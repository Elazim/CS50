"""Pipeline definitions.

`document_ingest` (M1): verify → checksum → parse → classify → pii_tag →
chunk_embed → finalize. Steps are idempotent — parse and chunk_embed clear
their own prior output for the document before writing, so a resumed or
re-run pipeline never duplicates rows.
"""

import hashlib
import uuid
from collections import Counter
from dataclasses import asdict

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.ai.chunker import chunk_elements
from app.ai.classify import classify_document
from app.ai.pii import detect_pii, summarize
from app.ai.providers import estimate_tokens, get_embedding_provider, record_usage
from app.errors import NotFoundError
from app.modules.documents.elements import Chunk, DocumentElement
from app.modules.documents.models import Document, DocumentStatus
from app.parsing.registry import parse_document
from app.storage import get_object_bytes, head_object
from app.worker.runner import StepContext, StepDef

EMBED_BATCH_SIZE = 64


def _document(session: Session, ctx: StepContext) -> Document:
    doc_id = ctx.run.context.get("document_id")
    doc = session.get(Document, uuid.UUID(doc_id)) if doc_id else None
    if doc is None:
        raise NotFoundError("Document referenced by run not found")
    return doc


def _elements(session: Session, doc: Document) -> list[DocumentElement]:
    return list(
        session.query(DocumentElement)
        .filter(DocumentElement.document_id == doc.id)
        .order_by(DocumentElement.order_key)
    )


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


def parse(session: Session, ctx: StepContext) -> tuple[dict, int]:
    doc = _document(session, ctx)
    data = get_object_bytes(doc.blob_key)
    parsed = parse_document(doc.filename, doc.mime, data)

    # Idempotency: this step owns the document's elements (and chunks cascade
    # from re-chunking later); clear prior output before writing.
    session.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    session.execute(delete(DocumentElement).where(DocumentElement.document_id == doc.id))

    for order, element in enumerate(parsed):
        session.add(
            DocumentElement(
                org_id=doc.org_id,
                document_id=doc.id,
                kind=element.kind,
                page=element.page,
                section_path=element.section_path,
                text=element.text,
                table_json=element.table_json,
                meta=element.meta,
                order_key=order,
            )
        )
    session.flush()
    return {"element_count": len(parsed)}, 0


def classify(session: Session, ctx: StepContext) -> tuple[dict, int]:
    doc = _document(session, ctx)
    sample = "\n".join(e.text for e in _elements(session, doc)[:40])
    doc.doc_class = classify_document(doc.filename, sample).value
    session.flush()
    return {"doc_class": doc.doc_class}, 0


def pii_tag(session: Session, ctx: StepContext) -> tuple[dict, int]:
    doc = _document(session, ctx)
    counts: Counter[str] = Counter()
    for element in _elements(session, doc):
        spans = detect_pii(element.text)
        if spans:
            element.meta = {**(element.meta or {}), "pii": [asdict(s) for s in spans]}
            counts.update(s.type for s in spans)
    doc.pii_summary = summarize(dict(counts))
    session.flush()
    return doc.pii_summary, 0


def chunk_embed(session: Session, ctx: StepContext) -> tuple[dict, int]:
    doc = _document(session, ctx)
    elements = _elements(session, doc)
    drafts = chunk_elements(elements)

    session.execute(delete(Chunk).where(Chunk.document_id == doc.id))

    provider = get_embedding_provider()
    total_tokens = 0
    for start in range(0, len(drafts), EMBED_BATCH_SIZE):
        batch = drafts[start : start + EMBED_BATCH_SIZE]
        embeddings = provider.embed([d.text for d in batch], input_type="document")
        for draft, embedding in zip(batch, embeddings, strict=True):
            total_tokens += draft.token_count
            session.add(
                Chunk(
                    org_id=doc.org_id,
                    project_id=doc.project_id,
                    document_id=doc.id,
                    element_ids=draft.element_ids,
                    text=draft.text,
                    token_count=draft.token_count,
                    embedding=embedding,
                    meta={"section_path": draft.section_path, "pages": draft.pages},
                )
            )
    record_usage(
        session,
        org_id=doc.org_id,
        project_id=doc.project_id,
        kind="embedding",
        provider=provider.name,
        model=provider.model,
        tokens_in=total_tokens,
        ref=f"document:{doc.id}",
    )
    session.flush()
    return {"chunk_count": len(drafts), "embedded_tokens": total_tokens}, total_tokens


def finalize(session: Session, ctx: StepContext) -> tuple[dict, int]:
    doc = _document(session, ctx)
    doc.status = DocumentStatus.ready
    session.flush()
    return {"status": doc.status.value}, 0


def estimate_document_tokens(doc: Document, session: Session) -> int:
    return sum(estimate_tokens(e.text) for e in _elements(session, doc))


from app.worker.knowledge_pipeline import (  # noqa: E402
    extract_knowledge,
    finalize_knowledge,
    resolve_entities,
)

PIPELINES: dict[str, list[StepDef]] = {
    "document_ingest": [
        StepDef("verify_blob", verify_blob),
        StepDef("checksum", checksum),
        StepDef("parse", parse, version="1"),
        StepDef("classify", classify, version="1"),
        StepDef("pii_tag", pii_tag, version="1"),
        StepDef("chunk_embed", chunk_embed, version="1"),
        StepDef("finalize", finalize),
    ],
    "knowledge_extract": [
        StepDef("extract", extract_knowledge, version="1"),
        StepDef("resolve", resolve_entities, version="1"),
        StepDef("finalize", finalize_knowledge, version="1"),
    ],
}
