import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import CurrentUser, get_db
from app.errors import NotFoundError, UnauthorizedError
from app.modules.accounts.models import Membership, Org
from app.modules.auth import service
from app.security import clear_session, issue_session

router = APIRouter(prefix="/auth", tags=["auth"])

WORKOS_API = "https://api.workos.com"


class DevLoginRequest(BaseModel):
    email: EmailStr
    name: str | None = None


class OrgSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    orgs: list[OrgSummary]


@router.post("/dev-login", response_model=MeResponse)
def dev_login(
    body: DevLoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> MeResponse:
    """Password-less login for local development.

    Registered only when auth_mode=dev; config validation refuses that mode
    in production (app.config).
    """
    user = service.get_or_create_user(db, email=body.email, name=body.name)
    service.ensure_default_org(db, user)
    db.flush()
    issue_session(response, user.id)
    return _me(db, user)


@router.get("/workos/login")
def workos_login() -> RedirectResponse:
    settings = get_settings()
    if not settings.workos_client_id:
        raise NotFoundError("WorkOS is not configured")
    params = (
        f"client_id={settings.workos_client_id}"
        "&provider=authkit&response_type=code"
        f"&redirect_uri={settings.web_origin}/api/auth/callback"
    )
    return RedirectResponse(f"{WORKOS_API}/user_management/authorize?{params}")


@router.get("/workos/callback")
def workos_callback(
    code: str,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    settings = get_settings()
    if not (settings.workos_api_key and settings.workos_client_id):
        raise NotFoundError("WorkOS is not configured")
    result = httpx.post(
        f"{WORKOS_API}/user_management/authenticate",
        json={
            "client_id": settings.workos_client_id,
            "client_secret": settings.workos_api_key,
            "grant_type": "authorization_code",
            "code": code,
        },
        timeout=15,
    )
    if result.status_code != 200:
        raise UnauthorizedError("WorkOS authentication failed")
    payload = result.json()["user"]
    name = " ".join(filter(None, [payload.get("first_name"), payload.get("last_name")])) or None
    user = service.get_or_create_user(
        db, email=payload["email"], name=name, workos_id=payload["id"]
    )
    service.ensure_default_org(db, user)
    db.flush()
    redirect = RedirectResponse(settings.web_origin)
    issue_session(redirect, user.id)
    return redirect


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> MeResponse:
    return _me(db, user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    clear_session(response)


def _me(db: Session, user) -> MeResponse:
    rows = db.execute(
        select(Org, Membership.role)
        .join(Membership, Membership.org_id == Org.id)
        .where(Membership.user_id == user.id, Org.deleted_at.is_(None))
        .order_by(Org.created_at)
    ).all()
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        orgs=[
            OrgSummary(id=org.id, name=org.name, slug=org.slug, role=role.value)
            for org, role in rows
        ],
    )
