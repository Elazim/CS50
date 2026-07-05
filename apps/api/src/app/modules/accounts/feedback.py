"""Feedback capture (docs/06 M5): every rating on generated output is a
labeled data point for deliverable quality — the correction flywheel's
simplest instrument."""

import enum
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.audit import audit
from app.db import Base, TimestampMixin, uuid7_pk
from app.deps import OrgCtx

router = APIRouter(tags=["feedback"])


class FeedbackSubject(enum.StrEnum):
    deliverable_version = "deliverable_version"
    entity = "entity"
    opportunity = "opportunity"


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    subject_type: Mapped[FeedbackSubject] = mapped_column(
        Enum(FeedbackSubject, name="feedback_subject")
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # +1 / -1
    comment: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(50), default="app")


class FeedbackIn(BaseModel):
    project_id: uuid.UUID | None = None
    subject_type: FeedbackSubject
    subject_id: uuid.UUID
    rating: int = Field(ge=-1, le=1)
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackOut(BaseModel):
    id: uuid.UUID

    model_config = {"from_attributes": True}


@router.post("/orgs/{org_id}/feedback", response_model=FeedbackOut, status_code=201)
def submit_feedback(body: FeedbackIn, ctx: OrgCtx) -> FeedbackOut:
    feedback = Feedback(
        org_id=ctx.org_id,
        project_id=body.project_id,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        rating=body.rating,
        comment=body.comment,
        created_by=ctx.user.id,
    )
    ctx.db.add(feedback)
    ctx.db.flush()
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id, action="feedback.submitted",
          resource_type=body.subject_type.value, resource_id=body.subject_id,
          meta={"rating": body.rating})
    return FeedbackOut.model_validate(feedback)
