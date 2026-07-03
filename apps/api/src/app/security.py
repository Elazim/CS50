"""Session cookie handling: signed, httpOnly, time-limited."""

import uuid

from fastapi import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

SESSION_COOKIE = "atc_session"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="atc.session")


def issue_session(response: Response, user_id: uuid.UUID) -> None:
    settings = get_settings()
    token = _serializer().dumps({"uid": str(user_id)})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.env not in ("dev", "test"),
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def read_session(token: str | None) -> uuid.UUID | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=get_settings().session_max_age_seconds)
        return uuid.UUID(data["uid"])
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        return None
