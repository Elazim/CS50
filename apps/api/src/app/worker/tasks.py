import uuid

from app.db import tenant_session
from app.logging import get_logger
from app.modules.pipelines.models import PipelineRun, RunStatus
from app.modules.pipelines.service import reflect_run_outcome
from app.worker.celery_app import celery_app
from app.worker.runner import execute_run

log = get_logger("worker")


@celery_app.task(name="pipelines.run", max_retries=2, default_retry_delay=10)
def run_pipeline(run_id: str, org_id: str) -> None:
    """Execute a pipeline run inside a tenant-bound session.

    Tenancy context arrives explicitly — a job without an org_id cannot
    touch tenant data (docs/05 §2).
    """
    with tenant_session(org_id) as session:
        run = session.get(PipelineRun, uuid.UUID(run_id))
        if run is None:
            log.error("run.missing", run_id=run_id)
            return
        if run.status in (RunStatus.succeeded, RunStatus.failed):
            log.info("run.already_terminal", run_id=run_id, status=run.status.value)
            return
        execute_run(session, run)
        reflect_run_outcome(session, run)
