from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import settings
from app.db.mongodb import get_database


class WhatsAppSendError(Exception):
    """Raised when a WhatsApp provider cannot deliver an outbound message."""


OTP_REDACTED_TEXT = "[OTP code redacted]"


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
    # An OTP body contains the code itself, which defeats storing only a hash in
    # otp_challenges. The bridge reads messageText off this row to actually send it, so
    # a queued row has to keep the text until delivery is acknowledged, at which point
    # acknowledge_outbound_message redacts it. Nothing ever collects a mock row, so that
    # one is redacted here and now.
    is_otp = str((raw_context or {}).get("source") or "").lower() == "otp"
    stored_text = OTP_REDACTED_TEXT if (is_otp and normalized_provider != "baileys") else message_text
    log = {
        "tenantId": tenant_id,
        "conversationId": conversation_id,
        "provider": normalized_provider,
        "direction": "outbound",
        "toPhone": to_phone,
        "messageText": stored_text,
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
