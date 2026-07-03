import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, uuid7_pk


class DocumentStatus(enum.StrEnum):
    pending_upload = "pending_upload"
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512))
    mime: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    blob_key: Mapped[str] = mapped_column(String(1024))
    doc_class: Mapped[str | None] = mapped_column(String(100))
    pii_summary: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"), default=DocumentStatus.pending_upload
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
