"""Document elements and chunks — the provenance layer (docs/04).

Elements are the atoms citations point at; they are immutable once written.
Chunks group elements for retrieval and carry both the vector embedding and
the lexical tsvector, so hybrid search is a single-database operation.
"""

import enum
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, uuid7_pk

# Voyage-3 / local hash embeddings share this dimension (app.ai.providers).
EMBEDDING_DIM = 1024


class ElementKind(enum.StrEnum):
    heading = "heading"
    paragraph = "paragraph"
    list_item = "list_item"
    table = "table"
    figure = "figure"
    slide = "slide"
    note = "note"


class DocumentElement(Base, TimestampMixin):
    __tablename__ = "document_elements"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ElementKind] = mapped_column(Enum(ElementKind, name="element_kind"))
    page: Mapped[int | None] = mapped_column(Integer)
    # Human-readable breadcrumb into the document: ["2. Intake", "2.1 Triage"]
    section_path: Mapped[list] = mapped_column(JSONB, default=list)
    text: Mapped[str] = mapped_column(Text)
    table_json: Mapped[dict | None] = mapped_column(JSONB)
    # PII spans and parser-specific details (docs/05 §4)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    order_key: Mapped[int] = mapped_column(Integer)


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    element_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class UsageEvent(Base, TimestampMixin):
    """Per-call AI cost metering (docs/02 §9) — COGS is measured, not guessed."""

    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(50))  # embedding | completion
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    ref: Mapped[str | None] = mapped_column(String(200))
