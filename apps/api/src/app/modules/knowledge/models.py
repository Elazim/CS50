"""The Project Knowledge Model (PKM) — the heart of the product (docs/04).

Entities + typed relations + evidence + review state. One entity table with
typed `attrs` (validated per-type in the service layer) rather than a table
per type: extraction, review, evidence, and search treat all types
uniformly. Anything relational (sequencing, ownership) is promoted to
`entity_relations`, never buried in JSON.
"""

import enum
import uuid

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, uuid7_pk


class Confidence(enum.StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class ReviewState(enum.StrEnum):
    ai_generated = "ai_generated"
    confirmed = "confirmed"
    edited = "edited"
    rejected = "rejected"


# Entity types are pack-extensible data, validated in the service layer —
# a DB enum would turn every new industry pack into a migration.
ENTITY_TYPES = {
    "actor",
    "system",
    "process",
    "process_step",
    "business_rule",
    "pain_point",
    "risk",
    "metric",
    "compliance_item",
}

RELATION_TYPES = {
    "performs",        # actor -> process_step
    "uses_system",     # process_step -> system
    "precedes",        # process_step -> process_step
    "hands_off_to",    # process_step -> actor
    "part_of",         # process_step -> process
    "governed_by",     # process -> business_rule / compliance_item
    "affects",         # pain_point -> process_step | process
}


class Entity(Base, TimestampMixin):
    __tablename__ = "entities"
    __table_args__ = (
        Index("ix_entities_project_type", "project_id", "type"),
    )

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(300))
    # Normalized for entity resolution ("FNOL Team" / "fnol team" collide here)
    canonical_name: Mapped[str] = mapped_column(String(300), index=True)
    attrs: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[Confidence] = mapped_column(Enum(Confidence, name="confidence"))
    review_state: Mapped[ReviewState] = mapped_column(
        Enum(ReviewState, name="review_state"), default=ReviewState.ai_generated
    )
    novel: Mapped[bool] = mapped_column(Boolean, default=False)  # out-of-ontology
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Extraction provenance: which extractor/pass produced it
    source: Mapped[str] = mapped_column(String(50), default="pipeline")


class EntityRelation(Base, TimestampMixin):
    __tablename__ = "entity_relations"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    from_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    to_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    rel_type: Mapped[str] = mapped_column(String(50))
    attrs: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[Confidence] = mapped_column(Enum(Confidence, name="confidence"))
    review_state: Mapped[ReviewState] = mapped_column(
        Enum(ReviewState, name="review_state"), default=ReviewState.ai_generated
    )


class Evidence(Base, TimestampMixin):
    """Polymorphic link from any assertion to its source elements.

    Every AI assertion must carry ≥1 evidence row or be explicitly flagged
    `estimate` — enforced by the knowledge service write path, not by
    convention (docs/04).
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_claimable", "claimable_type", "claimable_id"),
    )

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    claimable_type: Mapped[str] = mapped_column(String(50))  # entity | relation | ...
    claimable_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_elements.id", ondelete="CASCADE")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    quote: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)


class ReviewItemKind(enum.StrEnum):
    low_confidence = "low_confidence"
    merge_proposal = "merge_proposal"
    question = "question"


class ReviewItemStatus(enum.StrEnum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class ReviewItem(Base, TimestampMixin):
    """The analyst queue: the system asks instead of hallucinating."""

    __tablename__ = "review_items"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ReviewItemKind] = mapped_column(Enum(ReviewItemKind, name="review_item_kind"))
    subject_type: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    # merge proposals carry the other entity id in payload
    question: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[ReviewItemStatus] = mapped_column(
        Enum(ReviewItemStatus, name="review_item_status"), default=ReviewItemStatus.open
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolution: Mapped[dict | None] = mapped_column(JSONB)


class EntityHistory(Base, TimestampMixin):
    """Append-only change record: the PKM is a living current-state with
    history (docs/04 §3); every analyst correction is future eval data."""

    __tablename__ = "entity_history"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    change_source: Mapped[str] = mapped_column(String(50))  # pipeline | analyst
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict] = mapped_column(JSONB)
