import uuid

from sqlalchemy.orm import Session

from app.modules.pipelines.models import PipelineRun


def enqueue_run(
    db: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    kind: str,
    context: dict,
    trigger: str = "api",
) -> PipelineRun:
    """Create a run row and dispatch it to the worker.

    The task is sent after the row is flushed so the worker can always load
    it; Celery eager mode (tests) executes inline, which requires the row to
    be visible in the current transaction — the runner therefore accepts an
    existing session when running eagerly.
    """
    run = PipelineRun(
        org_id=org_id, project_id=project_id, kind=kind, context=context, trigger=trigger
    )
    db.add(run)
    db.flush()

    from app.config import get_settings
    from app.worker.tasks import run_pipeline  # late import: avoid celery at module import

    if get_settings().celery_task_always_eager:
        # Execute inline within the caller's transaction/session.
        from app.worker.runner import execute_run

        execute_run(db, run)
        reflect_run_outcome(db, run)
    else:
        db.commit()
        run_pipeline.delay(str(run.id), str(org_id))
    return run


def reflect_run_outcome(db: Session, run: PipelineRun) -> None:
    """Mirror a terminal run outcome onto the resource it operated on."""
    import uuid as _uuid

    from app.modules.documents.models import Document, DocumentStatus
    from app.modules.pipelines.models import RunStatus

    if run.kind == "document_ingest" and run.status == RunStatus.failed:
        doc_id = run.context.get("document_id")
        doc = db.get(Document, _uuid.UUID(doc_id)) if doc_id else None
        if doc is not None:
            doc.status = DocumentStatus.failed
