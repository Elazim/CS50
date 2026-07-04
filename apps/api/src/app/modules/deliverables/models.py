"""Deliverables: what leaves the building (docs/04 §3, docs/06 M4).

Versions are immutable: `spec` is the structured content, rendering to
each format is a pure function of it, and blob keys never change after
creation. Regeneration creates a new version — the answer to "what did we
show the exec committee in March" is always retrievable.
"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, uuid7_pk


class DeliverableType(enum.StrEnum):
    executive_summary = "executive_summary"
    current_state_assessment = "current_state_assessment"
    opportunity_register = "opportunity_register"
    roadmap_deck = "roadmap_deck"


class Deliverable(Base, TimestampMixin):
    __tablename__ = "deliverables"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[DeliverableType] = mapped_column(
        Enum(DeliverableType, name="deliverable_type")
    )
    title: Mapped[str] = mapped_column(String(300))
    latest_version: Mapped[int] = mapped_column(Integer, default=0)


class DeliverableVersion(Base, TimestampMixin):
    __tablename__ = "deliverable_versions"
    __table_args__ = (
        UniqueConstraint("deliverable_id", "version", name="uq_deliverable_version"),
    )

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    deliverable_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deliverables.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    # Structured content: sections, tables, figures, citations. Renderers
    # are pure functions of this — nothing appears in an export that isn't
    # in the spec.
    spec: Mapped[dict] = mapped_column(JSONB)
    # {"pptx": blob_key, "docx": ..., "xlsx": ..., "md": ...}
    artifacts: Mapped[dict] = mapped_column(JSONB, default=dict)
    generator_version: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
