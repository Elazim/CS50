"""M5: org admin, sample project, feedback, PDF export, and hardening."""

import io

import fitz
from sqlalchemy import select

from app.db import get_session_factory, set_org_context
from app.modules.accounts.feedback import Feedback
from tests.helpers import create_project  # noqa: F401  (shared fixture flows)


def _org(client, as_user):
    me = as_user("admin@example.com", "Admin")
    return me["orgs"][0]["id"]


# ---------- members & roles ----------


def test_member_lifecycle_and_role_enforcement(client, as_user):
    org_id = _org(client, as_user)

    added = client.post(
        f"/v1/orgs/{org_id}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    viewer_id = added.json()["user_id"]

    members = client.get(f"/v1/orgs/{org_id}/members").json()
    assert {m["email"] for m in members} == {"admin@example.com", "viewer@example.com"}

    # A viewer cannot create projects, invite members, or see the audit log.
    client.post("/v1/auth/logout")
    as_user("viewer@example.com")
    assert (
        client.post(f"/v1/orgs/{org_id}/projects", json={"name": "X"}).status_code == 403
    )
    assert (
        client.post(
            f"/v1/orgs/{org_id}/members", json={"email": "x@example.com"}
        ).status_code
        == 403
    )
    assert client.get(f"/v1/orgs/{org_id}/audit").status_code == 403

    # Promote to analyst → can create projects.
    client.post("/v1/auth/logout")
    as_user("admin@example.com")
    patched = client.patch(
        f"/v1/orgs/{org_id}/members/{viewer_id}", json={"role": "analyst"}
    )
    assert patched.json()["role"] == "analyst"
    client.post("/v1/auth/logout")
    as_user("viewer@example.com")
    assert (
        client.post(f"/v1/orgs/{org_id}/projects", json={"name": "X"}).status_code == 201
    )


def test_last_admin_is_protected(client, as_user):
    org_id = _org(client, as_user)
    me = client.get("/v1/auth/me").json()
    demote = client.patch(
        f"/v1/orgs/{org_id}/members/{me['id']}", json={"role": "viewer"}
    )
    assert demote.status_code == 400
    remove = client.delete(f"/v1/orgs/{org_id}/members/{me['id']}")
    assert remove.status_code == 400


def test_audit_log_records_admin_actions(client, as_user):
    org_id = _org(client, as_user)
    client.post(f"/v1/orgs/{org_id}/members", json={"email": "b@example.com"})
    events = client.get(f"/v1/orgs/{org_id}/audit").json()
    actions = {e["action"] for e in events}
    assert {"org.created", "member.added"} <= actions
    filtered = client.get(f"/v1/orgs/{org_id}/audit?action=member.added").json()
    assert all(e["action"] == "member.added" for e in filtered)
    assert filtered[0]["actor_email"] == "admin@example.com"


# ---------- sample project ----------


def test_sample_project_seeds_and_processes(client, as_user):
    org_id = _org(client, as_user)
    res = client.post(f"/v1/orgs/{org_id}/projects/sample")
    assert res.status_code == 201, res.text
    body = res.json()
    assert len(body["pipeline_run_ids"]) == 12

    documents = client.get(
        f"/v1/orgs/{org_id}/projects/{body['project']['id']}/documents"
    ).json()
    assert len(documents) == 12
    # Eager Celery in tests: everything already ingested.
    assert all(d["status"] == "ready" for d in documents)


# ---------- feedback ----------


def test_feedback_capture(client, as_user):
    org_id = _org(client, as_user)
    project = client.post(f"/v1/orgs/{org_id}/projects", json={"name": "P"}).json()
    res = client.post(
        f"/v1/orgs/{org_id}/feedback",
        json={
            "project_id": project["id"],
            "subject_type": "opportunity",
            "subject_id": project["id"],  # any uuid; polymorphic reference
            "rating": -1,
            "comment": "Score feels too optimistic",
        },
    )
    assert res.status_code == 201, res.text

    session = get_session_factory()()
    try:
        set_org_context(session, org_id)
        stored = session.execute(select(Feedback)).scalars().all()
        assert len(stored) == 1
        assert stored[0].rating == -1
        assert stored[0].comment == "Score feels too optimistic"
    finally:
        session.close()


# ---------- hardening ----------


def test_rate_limit_on_dev_login(client, as_user, monkeypatch):
    from app.config import get_settings
    from app.middleware import reset_rate_limits

    reset_rate_limits()
    monkeypatch.setattr(get_settings(), "rate_limit_auth", 3)
    statuses = [
        client.post(
            "/v1/auth/dev-login", json={"email": f"u{i}@example.com"}
        ).status_code
        for i in range(5)
    ]
    assert statuses[:3] == [200, 200, 200]
    assert 429 in statuses[3:]


def test_security_headers_present(client):
    res = client.get("/healthz")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"


def test_upload_extension_allowlist(client, as_user):
    org_id = _org(client, as_user)
    project = client.post(f"/v1/orgs/{org_id}/projects", json={"name": "P"}).json()
    res = client.post(
        f"/v1/orgs/{org_id}/projects/{project['id']}/documents",
        json={"filename": "malware.exe", "mime": "application/octet-stream",
              "size_bytes": 10},
    )
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["error"]["message"]


# ---------- PDF export ----------


def test_pdf_export_renders_and_reads_back(client, as_user):
    from evals import corpus

    from tests.helpers import ingest_document

    org_id = _org(client, as_user)
    project = client.post(f"/v1/orgs/{org_id}/projects", json={"name": "P"}).json()
    doc = next(d for d in corpus.build_corpus() if d.filename == "claims-intake-sop.md")
    ingest_document(client, org_id, project["id"], doc)
    for path in ("knowledge/extract", "opportunities/generate"):
        run = client.post(f"/v1/orgs/{org_id}/projects/{project['id']}/{path}")
        assert (
            client.get(
                f"/v1/orgs/{org_id}/pipeline-runs/{run.json()['pipeline_run_id']}"
            ).json()["status"]
            == "succeeded"
        )

    res = client.post(
        f"/v1/orgs/{org_id}/projects/{project['id']}/deliverables",
        json={"type": "executive_summary"},
    )
    deliverable_id = res.json()["deliverable"]["id"]
    version = client.get(
        f"/v1/orgs/{org_id}/deliverables/{deliverable_id}/versions"
    ).json()[0]
    assert "pdf" in version["formats"]

    download = client.get(
        f"/v1/orgs/{org_id}/deliverable-versions/{version['id']}/download",
        params={"format": "pdf"},
    )
    assert download.status_code == 200
    pdf = fitz.open(stream=io.BytesIO(download.content).read(), filetype="pdf")
    text = "\n".join(page.get_text() for page in pdf)
    assert "Executive Summary" in text
    assert "Sources" in text
    assert "analyst-reviewed" in text
