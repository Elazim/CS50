"""End-to-end upload flow: register → PUT to storage → complete → the
document_ingest pipeline (eager Celery) leaves the document ready."""

import hashlib

from app import storage
from app.config import get_settings


def _setup_project(client, as_user):
    me = as_user()
    org_id = me["orgs"][0]["id"]
    project = client.post(f"/v1/orgs/{org_id}/projects", json={"name": "P"}).json()
    return org_id, project["id"]


def _upload(client, org_id, project_id, content: bytes = b"claims SOP v1"):
    res = client.post(
        f"/v1/orgs/{org_id}/projects/{project_id}/documents",
        json={"filename": "sop.pdf", "mime": "application/pdf", "size_bytes": len(content)},
    )
    assert res.status_code == 201, res.text
    payload = res.json()
    assert "upload_url" in payload
    doc = payload["document"]
    assert doc["status"] == "pending_upload"
    # Simulate the browser's presigned PUT by writing the blob directly.
    key = f"org/{org_id}/projects/{project_id}/documents/{doc['id']}/sop.pdf"
    storage.s3_client().put_object(
        Bucket=get_settings().s3_bucket, Key=key, Body=content, ContentType="application/pdf"
    )
    return doc, content


def test_full_upload_and_ingest_flow(client, as_user):
    org_id, project_id = _setup_project(client, as_user)
    doc, content = _upload(client, org_id, project_id)

    completed = client.post(f"/v1/orgs/{org_id}/documents/{doc['id']}/complete")
    assert completed.status_code == 200, completed.text
    body = completed.json()
    run_id = body["pipeline_run_id"]

    run = client.get(f"/v1/orgs/{org_id}/pipeline-runs/{run_id}").json()
    assert run["status"] == "succeeded"
    assert [s["name"] for s in run["steps"]] == ["verify_blob", "checksum", "finalize"]
    assert all(s["status"] == "succeeded" for s in run["steps"])

    docs = client.get(f"/v1/orgs/{org_id}/projects/{project_id}/documents").json()
    assert docs[0]["status"] == "ready"
    assert docs[0]["content_hash"] == hashlib.sha256(content).hexdigest()
    assert docs[0]["latest_run_status"] == "succeeded"


def test_complete_without_blob_fails_cleanly(client, as_user):
    org_id, project_id = _setup_project(client, as_user)
    res = client.post(
        f"/v1/orgs/{org_id}/projects/{project_id}/documents",
        json={"filename": "ghost.pdf", "mime": "application/pdf", "size_bytes": 10},
    )
    doc_id = res.json()["document"]["id"]
    completed = client.post(f"/v1/orgs/{org_id}/documents/{doc_id}/complete")
    assert completed.status_code == 400
    assert "PUT the file first" in completed.json()["error"]["message"]


def test_oversized_upload_rejected(client, as_user):
    org_id, project_id = _setup_project(client, as_user)
    res = client.post(
        f"/v1/orgs/{org_id}/projects/{project_id}/documents",
        json={
            "filename": "huge.pdf",
            "mime": "application/pdf",
            "size_bytes": get_settings().max_upload_bytes + 1,
        },
    )
    assert res.status_code == 400
