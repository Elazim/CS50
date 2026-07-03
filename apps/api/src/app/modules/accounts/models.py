import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin, uuid7_pk


class Role(enum.StrEnum):
    org_admin = "org_admin"
    project_lead = "project_lead"
    analyst = "analyst"
    viewer = "viewer"


class Org(Base, TimestampMixin):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = uuid7_pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    plan: Mapped[str] = mapped_column(String(50), default="trial")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["Membership"]] = relationship(back_populates="org")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid7_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    workos_id: Mapped[str | None] = mapped_column(String(100), unique=True)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class Membership(Base, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id", name="uq_membership_user_org"),)

    id: Mapped[uuid.UUID] = uuid7_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE")
    )
    role: Mapped[Role] = mapped_column(Enum(Role, name="membership_role"))

    user: Mapped[User] = relationship(back_populates="memberships")
    org: Mapped[Org] = relationship(back_populates="memberships")
