"""Rate limiting and security headers (docs/05 §5).

The limiter is an in-process token bucket keyed by client IP and route
class — deliberately simple. It protects the expensive/abusable surfaces
(auth, uploads, pipeline triggers); a multi-instance deployment moves the
counters to Redis behind this same middleware seam.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings


@dataclass(frozen=True)
class Rule:
    prefix_or_suffix: str
    match: str  # "suffix" | "prefix_contains"
    limit: int
    window_seconds: int


def _rules(settings) -> list[Rule]:
    return [
        Rule("/auth/dev-login", "suffix", settings.rate_limit_auth, 60),
        Rule("/auth/workos/callback", "suffix", settings.rate_limit_auth, 60),
        Rule("/documents", "prefix_contains", settings.rate_limit_uploads, 60),
        Rule("/extract", "suffix", settings.rate_limit_pipelines, 60),
        Rule("/generate", "suffix", settings.rate_limit_pipelines, 60),
    ]


# Module-level so tests can reset it; per-process by design (see module doc).
_HITS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    _HITS.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits = _HITS

    async def dispatch(self, request: Request, call_next):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)
        settings = get_settings()
        path = request.url.path
        rule = next(
            (
                r for r in _rules(settings)
                if (r.match == "suffix" and path.endswith(r.prefix_or_suffix))
                or (r.match == "prefix_contains" and r.prefix_or_suffix in path)
            ),
            None,
        )
        if rule is not None:
            client_ip = request.client.host if request.client else "unknown"
            key = (client_ip, rule.prefix_or_suffix)
            now = time.monotonic()
            hits = self._hits[key]
            while hits and now - hits[0] > rule.window_seconds:
                hits.popleft()
            if len(hits) >= rule.limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many requests; slow down",
                        }
                    },
                    headers={"Retry-After": str(rule.window_seconds)},
                )
            hits.append(now)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/v1/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if get_settings().env in ("staging", "production"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
