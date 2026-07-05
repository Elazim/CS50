"""Org administration: members, roles, and the audit log viewer.

The audit log is a product feature for org admins (docs/04) — the same
table that satisfies enterprise review also answers "who changed what"
inside the product.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app.audit import AuditEvent, audit
from app.deps import OrgCtx
from app.errors import AppError, NotFoundError
from app.modules.accounts.models import Membership, Role, User
from app.modules.auth.service import get_or_create_user

router = APIRouter(tags=["admin"])


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str | None
    role: Role
    joined_at: datetime


class MemberInvite(BaseModel):
    email: EmailStr
    name: str | None = None
    role: Role = Role.analyst


class MemberRolePatch(BaseModel):
    role: Role


def _admin_count(ctx: OrgCtx) -> int:
    return ctx.db.execute(
        select(func.count()).select_from(Membership).where(
            Membership.org_id == ctx.org_id, Membership.role == Role.org_admin
        )
    ).scalar_one()


@router.get("/orgs/{org_id}/members", response_model=list[MemberOut])
def list_members(ctx: OrgCtx) -> list[MemberOut]:
    rows = ctx.db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.org_id == ctx.org_id)
        .order_by(Membership.created_at)
    ).all()
    return [
        MemberOut(
            user_id=user.id, email=user.email, name=user.name,
            role=membership.role, joined_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.post("/orgs/{org_id}/members", response_model=MemberOut, status_code=201)
def add_member(body: MemberInvite, ctx: OrgCtx) -> MemberOut:
    """Add a member by email. In dev-auth mode they sign in with that email
    directly; in WorkOS mode the membership attaches on their first SSO
    login (matched by email)."""
    ctx.require_role(Role.org_admin)
    user = get_or_create_user(ctx.db, email=body.email, name=body.name)
    ctx.db.flush()
    existing = ctx.db.execute(
        select(Membership).where(
            Membership.org_id == ctx.org_id, Membership.user_id == user.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError("User is already a member of this organization")
    membership = Membership(user_id=user.id, org_id=ctx.org_id, role=body.role)
    ctx.db.add(membership)
    ctx.db.flush()
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id, action="member.added",
          resource_type="user", resource_id=user.id,
          meta={"email": user.email, "role": body.role.value})
    return MemberOut(
        user_id=user.id, email=user.email, name=user.name,
        role=membership.role, joined_at=membership.created_at,
    )


@router.patch("/orgs/{org_id}/members/{user_id}", response_model=MemberOut)
def change_role(user_id: uuid.UUID, body: MemberRolePatch, ctx: OrgCtx) -> MemberOut:
    ctx.require_role(Role.org_admin)
    membership = ctx.db.execute(
        select(Membership).where(
            Membership.org_id == ctx.org_id, Membership.user_id == user_id
        )
    ).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Member not found")
    if (
        membership.role == Role.org_admin
        and body.role != Role.org_admin
        and _admin_count(ctx) <= 1
    ):
        raise AppError("Cannot demote the last org admin")
    membership.role = body.role
    ctx.db.flush()
    user = ctx.db.get_one(User, user_id)
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id, action="member.role_changed",
          resource_type="user", resource_id=user_id, meta={"role": body.role.value})
    return MemberOut(
        user_id=user.id, email=user.email, name=user.name,
        role=membership.role, joined_at=membership.created_at,
    )


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, ctx: OrgCtx) -> None:
    ctx.require_role(Role.org_admin)
    membership = ctx.db.execute(
        select(Membership).where(
            Membership.org_id == ctx.org_id, Membership.user_id == user_id
        )
    ).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Member not found")
    if membership.role == Role.org_admin and _admin_count(ctx) <= 1:
        raise AppError("Cannot remove the last org admin")
    ctx.db.delete(membership)
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id, action="member.removed",
          resource_type="user", resource_id=user_id)


class AuditEventOut(BaseModel):
    id: uuid.UUID
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    meta: dict
    at: datetime


@router.get("/orgs/{org_id}/audit", response_model=list[AuditEventOut])
def audit_log(
    ctx: OrgCtx, action: str | None = None, limit: int = 100, offset: int = 0
) -> list[AuditEventOut]:
    ctx.require_role(Role.org_admin)
    query = select(AuditEvent, User.email).outerjoin(
        User, User.id == AuditEvent.actor_id
    )
    if action:
        query = query.where(AuditEvent.action == action)
    rows = ctx.db.execute(
        query.order_by(AuditEvent.at.desc()).offset(offset).limit(min(limit, 500))
    ).all()
    return [
        AuditEventOut(
            id=event.id, actor_email=email, action=event.action,
            resource_type=event.resource_type, resource_id=event.resource_id,
            meta=event.meta, at=event.at,
        )
        for event, email in rows
    ]
