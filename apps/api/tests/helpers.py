"""Shared flows used by M1 integration and eval tests."""

from evals.corpus import CorpusDoc

from app import storage
from app.config import get_settings


def create_project(client, as_user, name: str = "Eval Project"):
    me = as_user()
    org_id = me["orgs"][0]["id"]
    project_id = client.post(f"/v1/orgs/{org_id}/projects", json={"name": name}).json()["id"]
    return org_id, project_id


def ingest_document(client, org_id: str, project_id: str, doc: CorpusDoc) -> dict:
    """Full API upload flow; eager Celery runs the ingest pipeline inline."""
    res = client.post(
        f"/v1/orgs/{org_id}/projects/{project_id}/documents",
        json={"filename": doc.filename, "mime": doc.mime, "size_bytes": len(doc.data)},
    )
    assert res.status_code == 201, res.text
    registered = res.json()["document"]
    key = (
        f"org/{org_id}/projects/{project_id}/documents/{registered['id']}/{doc.filename}"
    )
    storage.s3_client().put_object(
        Bucket=get_settings().s3_bucket, Key=key, Body=doc.data, ContentType=doc.mime
    )
    completed = client.post(f"/v1/orgs/{org_id}/documents/{registered['id']}/complete")
    assert completed.status_code == 200, completed.text
    return completed.json()["document"]
