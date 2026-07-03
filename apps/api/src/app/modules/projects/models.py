import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, uuid7_pk


class ProjectStatus(enum.StrEnum):
    active = "active"
    archived = "archived"


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    industry_pack: Mapped[str] = mapped_column(String(100), default="insurance-claims")
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.active
    )
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
