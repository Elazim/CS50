import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import set_org_context
from app.modules.accounts.models import Membership, Org, Role, User


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "workspace"
    return f"{slug[:40]}-{secrets.token_hex(3)}"


def get_or_create_user(
    db: Session, *, email: str, name: str | None = None, workos_id: str | None = None
) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, name=name, workos_id=workos_id)
        db.add(user)
        db.flush()
    else:
        if name and not user.name:
            user.name = name
        if workos_id and not user.workos_id:
            user.workos_id = workos_id
    return user


def ensure_default_org(db: Session, user: User) -> Org:
    """First sign-in bootstraps a personal workspace with the user as admin."""
    membership = db.execute(
        select(Membership).where(Membership.user_id == user.id).limit(1)
    ).scalar_one_or_none()
    if membership is not None:
        return db.get_one(Org, membership.org_id)

    display = user.name or user.email.split("@")[0]
    org = Org(name=f"{display}'s Workspace", slug=_slugify(display))
    db.add(org)
    db.flush()
    db.add(Membership(user_id=user.id, org_id=org.id, role=Role.org_admin))
    # The audit table is tenant-scoped; bind the freshly created org's
    # context so RLS accepts its bootstrap event.
    set_org_context(db, org.id)
    audit(
        db,
        org_id=org.id,
        actor_id=user.id,
        action="org.created",
        resource_type="org",
        resource_id=org.id,
        meta={"bootstrap": True},
    )
    return org
