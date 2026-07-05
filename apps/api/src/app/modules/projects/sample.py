"""One-click sample project (docs/06 M5 onboarding).

Seeds the synthetic Northbridge Mutual corpus into a fresh project and
kicks off ingestion — a design partner sees the full loop working before
uploading a single real document. No environment ever needs customer data
to be demonstrable (docs/05 §1).
"""

import uuid

from sqlalchemy.orm import Session

from app.modules.documents.models import Document, DocumentStatus
from app.modules.pipelines.service import enqueue_run
from app.modules.projects.models import Project
from app.storage import document_blob_key, put_object_bytes

SAMPLE_PROJECT_NAME = "Sample — Northbridge Mutual Claims"


def seed_sample_project(
    session: Session, *, org_id: uuid.UUID
) -> tuple[Project, list[uuid.UUID]]:
    from app.sample_corpus import build_corpus

    project = Project(org_id=org_id, name=SAMPLE_PROJECT_NAME)
    session.add(project)
    session.flush()

    run_ids: list[uuid.UUID] = []
    for corpus_doc in build_corpus():
        document = Document(
            org_id=org_id,
            project_id=project.id,
            filename=corpus_doc.filename,
            mime=corpus_doc.mime,
            size_bytes=len(corpus_doc.data),
            blob_key="",
            status=DocumentStatus.processing,
        )
        session.add(document)
        session.flush()
        document.blob_key = document_blob_key(
            org_id, project.id, document.id, corpus_doc.filename
        )
        put_object_bytes(document.blob_key, corpus_doc.data, corpus_doc.mime)
        run = enqueue_run(
            session, org_id=org_id, project_id=project.id,
            kind="document_ingest", context={"document_id": str(document.id)},
            trigger="sample_seed",
        )
        run_ids.append(run.id)
    return project, run_ids
