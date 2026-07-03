import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin, uuid7_pk


class RunStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class StepStatus(enum.StrEnum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


class PipelineRun(Base, TimestampMixin):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(100))
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status"), default=RunStatus.queued
    )
    trigger: Mapped[str] = mapped_column(String(100), default="api")
    # Subject the run operates on (M0: a document id). JSONB so later pipeline
    # kinds (corpus-wide extraction, generation) can carry richer context.
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list["PipelineStep"]] = relationship(
        back_populates="run", order_by="PipelineStep.created_at"
    )


class PipelineStep(Base, TimestampMixin):
    __tablename__ = "pipeline_steps"
    __table_args__ = (UniqueConstraint("run_id", "name", name="uq_pipeline_step_run_name"),)

    id: Mapped[uuid.UUID] = uuid7_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[StepStatus] = mapped_column(Enum(StepStatus, name="step_status"))
    # Cache key: hash of (step inputs, step version). A step whose input_hash
    # matches a prior success is skipped on retry — the checkpoint pattern
    # that makes Celery safe for multi-step pipelines (docs/02 §3).
    input_hash: Mapped[str] = mapped_column(String(64))
    output_ref: Mapped[dict | None] = mapped_column(JSONB)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    cost_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[PipelineRun] = relationship(back_populates="steps")
