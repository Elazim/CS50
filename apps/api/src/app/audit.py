"""Append-only audit trail — a product feature, not an ops log (docs/04).

All writes go through `audit()` so the shape stays uniform. The migration
revokes UPDATE/DELETE on this table; append-only is enforced by the
database, not by convention.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base, uuid7_pk


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = uuid7_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def audit(
    session: Session,
    *,
    org_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | str | None = None,
    actor_id: uuid.UUID | None = None,
    meta: dict | None = None,
    ip: str | None = None,
) -> None:
    session.add(
        AuditEvent(
            org_id=org_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            meta=meta or {},
            ip=ip,
        )
    )
