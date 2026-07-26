from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id to every request/response for easier debugging."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Small, dependency-free security headers for browser-facing API responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.app_env == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory per-IP rate limiter for demo/small deployments.

    It is intentionally disabled by default because production deployments should normally use a
    gateway-level limiter. Enabling RATE_LIMIT_ENABLED=true gives the FYP/demo app a basic safety
    net without adding Redis or a paid service.
    """

    _hits: dict[str, Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled or request.url.path.endswith("/health"):
            return await call_next(request)

        now = time.monotonic()
        window_seconds = 60
        max_hits = settings.rate_limit_requests_per_minute
        client_ip = request.client.host if request.client else "unknown"
        bucket = self._hits[client_ip]

        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

        if len(bucket) >= max_hits:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "message": "Too many requests. Please try again after a minute.",
                    "data": None,
                    "meta": {"retryAfterSeconds": window_seconds},
                },
                headers={"Retry-After": str(window_seconds)},
            )

        bucket.append(now)
        return await call_next(request)
