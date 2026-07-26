from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.db.mongodb import get_database


class SmsSendError(Exception):
    """Raised when an SMS provider cannot deliver an outbound message."""


def _normalize_provider(provider: str | None) -> str:
    normalized = str(provider or settings.sms_provider or "mock").strip().lower()
    return normalized if normalized in {"mock", "http"} else "mock"


async def send_sms_text(
    *,
    tenant_id,
    provider: str | None = None,
    to_phone: str,
    message_text: str,
    raw_context: dict | None = None,
) -> dict:
    """Send an SMS text message.

    The mock provider writes a delivery log only. The generic HTTP branch is a
    low-cost integration seam for FYP demos and future providers such as local
    SMS gateways. It intentionally uses simple headers/body so it can be adapted
    without changing business logic.
    """
    db = get_database()
    normalized_provider = _normalize_provider(provider)
    now = datetime.now(timezone.utc)
    log = {
        "tenantId": tenant_id,
        "provider": normalized_provider,
        "direction": "outbound",
        "toPhone": to_phone,
        "messageText": message_text[:600],
        "deliveryStatus": "queued",
        "rawContext": raw_context or {},
        "createdAt": now,
        "updatedAt": now,
    }

    if normalized_provider == "mock":
        log.update(
            {
                "deliveryStatus": "mock_sent",
                "providerMessageId": f"mock-sms-{int(now.timestamp())}",
                "providerResponse": {"mock": True, "note": "SMS was logged locally instead of sent to a paid gateway."},
            }
        )
        log["_id"] = (await db.sms_message_logs.insert_one(log)).inserted_id
        return log

    if not settings.sms_http_url or not settings.sms_api_key:
        log.update({"deliveryStatus": "failed", "error": "Missing SMS_HTTP_URL or SMS_API_KEY."})
        log["_id"] = (await db.sms_message_logs.insert_one(log)).inserted_id
        raise SmsSendError(log["error"])

    payload = {
        "to": to_phone,
        "message": message_text[:600],
        "sender": settings.sms_sender_id,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                settings.sms_http_url,
                headers={"Authorization": f"Bearer {settings.sms_api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            try:
                provider_response = response.json()
            except Exception:
                provider_response = {"text": response.text}
        log.update({"deliveryStatus": "sent", "providerResponse": provider_response})
        log["_id"] = (await db.sms_message_logs.insert_one(log)).inserted_id
        return log
    except Exception as exc:
        log.update({"deliveryStatus": "failed", "error": str(exc)})
        log["_id"] = (await db.sms_message_logs.insert_one(log)).inserted_id
        raise SmsSendError(str(exc)) from exc
