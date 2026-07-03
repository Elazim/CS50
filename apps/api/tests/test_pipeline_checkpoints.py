"""The checkpoint pattern (docs/02 §3): a retried run skips steps that
already succeeded with the same inputs, instead of redoing them."""

import uuid

from app import storage
from app.config import get_settings
from app.db import get_session_factory, set_org_context
from app.modules.pipelines.models import PipelineRun, RunStatus
from app.worker.runner import execute_run


def _ingested_document(client, as_user):
    me = as_user()
    org_id = me["orgs"][0]["id"]
    project_id = client.post(f"/v1/orgs/{org_id}/projects", json={"name": "P"}).json()["id"]
    content = b"# Procedure\n\nA short but real document.\n"
    res = client.post(
        f"/v1/orgs/{org_id}/projects/{project_id}/documents",
        json={"filename": "a.md", "mime": "text/markdown", "size_bytes": len(content)},
    )
    doc = res.json()["document"]
    key = f"org/{org_id}/projects/{project_id}/documents/{doc['id']}/a.md"
    storage.s3_client().put_object(Bucket=get_settings().s3_bucket, Key=key, Body=content)
    run_id = client.post(f"/v1/orgs/{org_id}/documents/{doc['id']}/complete").json()[
        "pipeline_run_id"
    ]
    return org_id, run_id


def test_retry_skips_completed_steps(client, as_user):
    org_id, run_id = _ingested_document(client, as_user)

    session = get_session_factory()()
    try:
        set_org_context(session, org_id)
        run = session.get(PipelineRun, uuid.UUID(run_id))
        assert run.status == RunStatus.succeeded
        first_attempts = {s.name: s.attempt for s in run.steps}

        # Simulate a broker redelivery: force the run non-terminal and re-execute.
        run.status = RunStatus.queued
        session.flush()
        execute_run(session, run)
        session.commit()

        assert run.status == RunStatus.succeeded
        for step in run.steps:
            assert step.attempt == first_attempts[step.name], (
                f"step {step.name} re-ran despite matching checkpoint"
            )
    finally:
        session.close()
