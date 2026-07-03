"""Request dependencies: session, current user, and tenant context.

The tenancy rule (docs/05 §2): handlers touching tenant data get their
session through `OrgContext`, which (1) verifies membership and role and
(2) binds the transaction to the org via the RLS GUC. A handler can't
accidentally query across tenants — the database returns zero rows.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session_factory, set_org_context
from app.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.modules.accounts.models import Membership, Role, User
from app.security import SESSION_COOKIE, read_session

# Role ordering for "at least" checks.
_ROLE_RANK = {Role.viewer: 0, Role.analyst: 1, Role.project_lead: 2, Role.org_admin: 3}


def get_db() -> Iterator[Session]:
    """Plain session for pre-tenant operations (auth, org listing) only."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    atc_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    user_id = read_session(atc_session)
    if user_id is None:
        raise UnauthorizedError("Not signed in")
    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Unknown session user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass
class OrgContext:
    org_id: uuid.UUID
    user: User
    role: Role
    db: Session

    def require_role(self, minimum: Role) -> None:
        if _ROLE_RANK[self.role] < _ROLE_RANK[minimum]:
            raise ForbiddenError(f"Requires {minimum.value} role")


def get_org_context(
    org_id: Annotated[uuid.UUID, Path()],
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> OrgContext:
    membership = db.execute(
        select(Membership).where(Membership.user_id == user.id, Membership.org_id == org_id)
    ).scalar_one_or_none()
    if membership is None:
        # 404, not 403: don't confirm the org exists to non-members.
        raise NotFoundError("Organization not found")
    set_org_context(db, org_id)
    return OrgContext(org_id=org_id, user=user, role=membership.role, db=db)


OrgCtx = Annotated[OrgContext, Depends(get_org_context)]
