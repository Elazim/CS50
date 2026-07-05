import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.audit import audit
from app.config import get_settings
from app.deps import OrgCtx
from app.errors import AppError, NotFoundError
from app.modules.accounts.models import Role
from app.modules.documents.elements import DocumentElement
from app.modules.documents.models import Document, DocumentStatus
from app.modules.pipelines.models import PipelineRun, RunStatus
from app.modules.pipelines.service import enqueue_run
from app.modules.projects.models import Project
from app.parsing.registry import SUPPORTED_EXTENSIONS
from app.storage import document_blob_key, head_object, presign_put

router = APIRouter(tags=["documents"])


class DocumentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    mime: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)


class DocumentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    mime: str
    size_bytes: int | None
    content_hash: str | None
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadOut(BaseModel):
    document: DocumentOut
    upload_url: str


class DocumentCompleteOut(BaseModel):
    document: DocumentOut
    pipeline_run_id: uuid.UUID


@router.post(
    "/orgs/{org_id}/projects/{project_id}/documents",
    response_model=DocumentUploadOut,
    status_code=201,
)
def create_document_upload(
    project_id: uuid.UUID, body: DocumentCreate, ctx: OrgCtx
) -> DocumentUploadOut:
    """Step 1 of upload: register the document, hand back a presigned PUT URL.

    The browser uploads directly to object storage — document bytes never
    stream through the API process.
    """
    ctx.require_role(Role.analyst)
    if body.size_bytes > get_settings().max_upload_bytes:
        raise AppError("File exceeds the upload size limit")
    extension = body.filename.rsplit(".", 1)[-1].lower() if "." in body.filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError(
            f"Unsupported file type '.{extension}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    project = ctx.db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFoundError("Project not found")

    doc = Document(
        org_id=ctx.org_id,
        project_id=project_id,
        filename=body.filename,
        mime=body.mime,
        size_bytes=body.size_bytes,
        blob_key="",
    )
    ctx.db.add(doc)
    ctx.db.flush()
    doc.blob_key = document_blob_key(ctx.org_id, project_id, doc.id, body.filename)
    upload_url = presign_put(doc.blob_key, body.mime)
    return DocumentUploadOut(document=DocumentOut.model_validate(doc), upload_url=upload_url)


@router.post(
    "/orgs/{org_id}/documents/{document_id}/complete",
    response_model=DocumentCompleteOut,
)
def complete_document_upload(document_id: uuid.UUID, ctx: OrgCtx) -> DocumentCompleteOut:
    """Step 2: confirm the blob landed, then kick off the ingestion pipeline."""
    ctx.require_role(Role.analyst)
    doc = ctx.db.get(Document, document_id)
    if doc is None or doc.deleted_at is not None:
        raise NotFoundError("Document not found")
    if doc.status != DocumentStatus.pending_upload:
        raise AppError(f"Document is already {doc.status.value}")

    head = head_object(doc.blob_key)
    if head is None:
        raise AppError("Upload not found in storage; PUT the file first")
    doc.size_bytes = head.get("ContentLength", doc.size_bytes)
    # Mark processing before dispatch: in eager mode (tests) the pipeline runs
    # inline and its `finalize` step must be the last writer of doc.status.
    doc.status = DocumentStatus.processing

    run = enqueue_run(
        ctx.db,
        org_id=ctx.org_id,
        project_id=doc.project_id,
        kind="document_ingest",
        context={"document_id": str(doc.id)},
    )
    audit(
        ctx.db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="document.uploaded",
        resource_type="document",
        resource_id=doc.id,
        meta={"filename": doc.filename, "pipeline_run_id": str(run.id)},
    )
    return DocumentCompleteOut(document=DocumentOut.model_validate(doc), pipeline_run_id=run.id)


class ElementOut(BaseModel):
    id: uuid.UUID
    kind: str
    page: int | None
    section_path: list
    text: str
    table_json: dict | None
    pii_types: list[str] = []
    order_key: int

    model_config = {"from_attributes": True}


class DocumentDetailOut(BaseModel):
    document: DocumentOut
    doc_class: str | None
    pii_summary: dict | None
    element_count: int
    elements: list[ElementOut]


@router.get("/orgs/{org_id}/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(
    document_id: uuid.UUID,
    ctx: OrgCtx,
    offset: int = 0,
    limit: int = 500,
) -> DocumentDetailOut:
    doc = ctx.db.get(Document, document_id)
    if doc is None or doc.deleted_at is not None:
        raise NotFoundError("Document not found")
    total = ctx.db.execute(
        select(func.count()).select_from(DocumentElement).where(
            DocumentElement.document_id == doc.id
        )
    ).scalar_one()
    elements = (
        ctx.db.execute(
            select(DocumentElement)
            .where(DocumentElement.document_id == doc.id)
            .order_by(DocumentElement.order_key)
            .offset(offset)
            .limit(min(limit, 1000))
        )
        .scalars()
        .all()
    )
    element_out = []
    for element in elements:
        item = ElementOut.model_validate(element)
        pii_spans = (element.meta or {}).get("pii", [])
        item.pii_types = sorted({span["type"] for span in pii_spans})
        element_out.append(item)
    return DocumentDetailOut(
        document=DocumentOut.model_validate(doc),
        doc_class=doc.doc_class,
        pii_summary=doc.pii_summary,
        element_count=total,
        elements=element_out,
    )


class DocumentListItem(DocumentOut):
    doc_class: str | None = None
    latest_run_id: uuid.UUID | None = None
    latest_run_status: RunStatus | None = None


@router.get(
    "/orgs/{org_id}/projects/{project_id}/documents",
    response_model=list[DocumentListItem],
)
def list_documents(project_id: uuid.UUID, ctx: OrgCtx) -> list[DocumentListItem]:
    docs = (
        ctx.db.execute(
            select(Document)
            .where(Document.project_id == project_id, Document.deleted_at.is_(None))
            .order_by(Document.created_at.desc())
        )
        .scalars()
        .all()
    )
    # Latest ingest run per document, resolved in one query over the project.
    runs = (
        ctx.db.execute(
            select(PipelineRun)
            .where(PipelineRun.project_id == project_id, PipelineRun.kind == "document_ingest")
            .order_by(PipelineRun.created_at)
        )
        .scalars()
        .all()
    )
    latest_by_doc: dict[str, PipelineRun] = {}
    for run in runs:
        doc_id = run.context.get("document_id")
        if doc_id:
            latest_by_doc[doc_id] = run

    out = []
    for doc in docs:
        item = DocumentListItem.model_validate(doc)
        latest = latest_by_doc.get(str(doc.id))
        if latest is not None:
            item.latest_run_id = latest.id
            item.latest_run_status = latest.status
        out.append(item)
    return out
