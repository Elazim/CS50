import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import DateTime, create_engine, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from uuid6 import uuid7

from app.config import get_settings

_engine = None
_session_factory = None


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


def reset_engine() -> None:
    """Dispose the cached engine (used by tests when settings change)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def uuid7_pk() -> Mapped[uuid.UUID]:
    """Time-ordered UUIDv7 primary key column (index-friendly, docs/04)."""
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)


def set_org_context(session: Session, org_id: uuid.UUID | str) -> None:
    """Bind the session's transaction to one tenant.

    Every RLS policy checks `app.org_id`; a session without it sees zero
    tenant rows. `set_config(..., true)` is transaction-local, so the
    context cannot leak across pooled connections.
    """
    session.execute(
        text("SELECT set_config('app.org_id', :org_id, true)"),
        {"org_id": str(org_id)},
    )


@contextmanager
def tenant_session(org_id: uuid.UUID | str) -> Iterator[Session]:
    """Session pre-bound to a tenant — the only entrypoint workers may use."""
    session = get_session_factory()()
    try:
        set_org_context(session, org_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
