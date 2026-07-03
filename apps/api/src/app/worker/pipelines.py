"""Pipeline definitions.

M0 ships `document_ingest` as the proof of the checkpoint pattern end to
end (queue → blob storage → DB state → SSE progress). M1 replaces its body
with real parsing/OCR/chunking steps behind the same runner contract.
"""

import hashlib
import uuid

from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.modules.documents.models import Document, DocumentStatus
from app.storage import get_object_bytes, head_object
from app.worker.runner import StepContext, StepDef


def _document(session: Session, ctx: StepContext) -> Document:
    doc_id = ctx.run.context.get("document_id")
    doc = session.get(Document, uuid.UUID(doc_id)) if doc_id else None
    if doc is None:
        raise NotFoundError("Document referenced by run not found")
    return doc


def verify_blob(session: Session, ctx: StepContext) -> tuple[dict, int]:
    doc = _document(session, ctx)
    head = head_object(doc.blob_key)
    if head is None:
        raise FileNotFoundError(f"Blob missing: {doc.blob_key}")
    return {"size_bytes": head.get("ContentLength"), "etag": head.get("ETag")}, 0


def checksum(session: Session, ctx: StepContext) -> tuple[dict, int]:
    doc = _document(session, ctx)
    data = get_object_bytes(doc.blob_key)
    doc.content_hash = hashlib.sha256(data).hexdigest()
    session.flush()
    return {"content_hash": doc.content_hash}, 0


def finalize(session: Session, ctx: StepContext) -> tuple[dict, int]:
    doc = _document(session, ctx)
    doc.status = DocumentStatus.ready
    session.flush()
    return {"status": doc.status.value}, 0


PIPELINES: dict[str, list[StepDef]] = {
    "document_ingest": [
        StepDef("verify_blob", verify_blob),
        StepDef("checksum", checksum),
        StepDef("finalize", finalize),
    ],
}
