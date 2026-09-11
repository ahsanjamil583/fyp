from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import settings
from app.db.mongodb import get_database


class WhatsAppSendError(Exception):
    """Raised when a WhatsApp provider cannot deliver an outbound message."""


def _normalize_provider(provider: str | None) -> str:
    normalized = str(provider or settings.whatsapp_provider or "mock").strip().lower()
    return normalized if normalized in {"mock", "baileys"} else "mock"


async def send_whatsapp_text(
    *,
    tenant_id,
    conversation_id=None,
    provider: str | None = None,
    to_phone: str,
    message_text: str,
    integration: dict | None = None,
    raw_context: dict | None = None,
) -> dict:
    """Store an outbound WhatsApp message log for mock or bridge-based providers."""
    db = get_database()
    normalized_provider = _normalize_provider(provider)
    now = datetime.now(timezone.utc)
    direct_reply = (raw_context or {}).get("source") == "whatsapp_agent_auto_reply"
    log = {
        "tenantId": tenant_id,
        "conversationId": conversation_id,
        "provider": normalized_provider,
        "direction": "outbound",
        "toPhone": to_phone,
        "messageText": message_text,
        "deliveryStatus": ("returned_to_bridge" if direct_reply else "queued") if normalized_provider == "baileys" else "mock_sent",
        "providerMessageId": f"{normalized_provider}-{int(now.timestamp())}",
        "providerResponse": {
            "mock": normalized_provider == "mock",
            "bridge": normalized_provider == "baileys",
            "note": (
                ("Reply was returned to the bridge." if direct_reply else "Queued for the connected WhatsApp bridge.")
                if normalized_provider == "baileys"
                else "Message was logged locally instead of sent to WhatsApp."
            ),
        },
        "rawContext": raw_context or {},
        "createdAt": now,
        "updatedAt": now,
    }
    log["_id"] = (await db.whatsapp_message_logs.insert_one(log)).inserted_id
    return log
