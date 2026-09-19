from __future__ import annotations

import logging
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.rate_limit import check_rate_limit, resolve_rule

logger = logging.getLogger(__name__)


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


def _resolve_client_ip(request: Request) -> str:
    """The address the rate limiter should count against.

    Behind a load balancer every request arrives from the proxy, so keying on the socket
    peer puts all users in one bucket. X-Forwarded-For carries the real client, but it
    is caller-supplied and trivially spoofed, so it is only believed when the immediate
    peer is a proxy the operator has explicitly listed in TRUSTED_PROXY_IPS.
    """
    peer = request.client.host if request.client else ""
    trusted = settings.trusted_proxy_ips or []
    if trusted and (("*" in trusted) or (peer in trusted)):
        forwarded = request.headers.get("x-forwarded-for", "")
        # Left-most entry is the original client; the rest are intermediate proxies.
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return peer or "unknown"


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    """Applies the per-route budgets declared in ``app.core.rate_limit``.

    Health checks are exempt so a throttled client cannot make the service look down to
    a load balancer.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # A substring test also exempted every tenant whose slug begins with "health",
        # for example /public/businesses/health-clinic/chat/messages.
        if not settings.rate_limit_enabled or path.startswith(f"{settings.api_v1_prefix}/health"):
            return await call_next(request)

        rule = resolve_rule(request.method, path)
        client_ip = _resolve_client_ip(request)
        allowed, retry_after = await check_rate_limit(rule, client_ip)

        if not allowed:
            logger.warning("Rate limit hit: rule=%s ip=%s path=%s", rule.name, client_ip, path)
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "message": "Too many requests. Please slow down and try again shortly.",
                    "data": None,
                    "meta": {"retryAfterSeconds": retry_after, "limit": rule.name},
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
