from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.integrations.whatsapp.provider import WhatsAppSendError, send_whatsapp_text
from app.schemas.whatsapp_schema import (
    WhatsAppBridgeInboundRequest,
    WhatsAppBridgeStatusRequest,
    WhatsAppMockInboundRequest,
    WhatsAppOutboundRequest,
    WhatsAppSettingsRequest,
)
from app.services.ai_chat_service import build_ai_reply, detect_language_mode, load_conversation_messages, save_message
from app.services.business_notification_service import create_business_notification

HANDOFF_REPLY = "I have marked this conversation for owner handoff. The business team can review it from the dashboard."
DEFAULT_FALLBACK_REPLY = "Sorry, main is waqt WhatsApp reply complete nahi kar pa raha. Business owner ko notify kar diya gaya hai."
DEFAULT_HANDOFF_KEYWORDS = ["human", "agent", "admin", "owner", "representative", "call me", "insan", "baat karni"]


def normalize_phone(value: str | None) -> str:
    phone = re.sub(r"[^0-9+]", "", str(value or "").strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if phone and not phone.startswith("+"):
        if phone.startswith("0") and len(phone) >= 10:
            phone = "+92" + phone[1:]
        elif phone.startswith("92"):
            phone = "+" + phone
    return phone


def build_whatsapp_deep_link(phone: str | None, text: str = "") -> str:
    digits = re.sub(r"\D", "", normalize_phone(phone))
    if not digits:
        return ""
    url = f"https://wa.me/{digits}"
    if text:
        from urllib.parse import quote

        url = f"{url}?text={quote(text)}"
    return url


def serialize_whatsapp_settings(settings_doc: dict | None, tenant: dict | None = None) -> dict:
    # Two phone formats exist on purpose: normalize_pk_phone enforces the strict local
    # 03XXXXXXXXX used for accounts and OTP, while normalize_phone here is lenient E.164
    # because a WhatsApp customer can be in any country. Everything stored against an
    # integration uses the E.164 form so lookups match, including the contact fallback.
    tenant_contact = (tenant or {}).get("contact") or {}
    business_number = normalize_phone(
        (settings_doc or {}).get("businessWhatsAppNumber") or tenant_contact.get("whatsapp") or ""
    )
    if not settings_doc:
        return {
            "id": "",
            "tenantId": str((tenant or {}).get("_id", "")),
            "provider": settings.whatsapp_provider,
            "businessWhatsAppNumber": business_number,
            "normalizedBusinessWhatsAppNumber": normalize_phone(business_number),
            "displayName": (tenant or {}).get("name", ""),
            "webhookVerifyToken": settings.whatsapp_verify_token,
            "isConnected": False,
            "agentEnabled": True,
            "autoReplyEnabled": True,
            "handoffEnabled": True,
            "handoffKeywords": DEFAULT_HANDOFF_KEYWORDS,
            "welcomeMessage": "Assalam o Alaikum! Main BizXus AI assistant hoon. Aap products, prices, timing ya order ke bare mein pooch sakte hain.",
            "fallbackReply": DEFAULT_FALLBACK_REPLY,
            "businessHoursMode": "always_on",
            "status": "not_configured",
            "lastInboundAt": None,
            "lastOutboundAt": None,
        }
    data = serialize_document(settings_doc)
    data["businessWhatsAppNumber"] = business_number
    data["normalizedBusinessWhatsAppNumber"] = normalize_phone(business_number)
    data["webhookVerifyToken"] = data.get("webhookVerifyToken") or settings.whatsapp_verify_token
    return data


def _serialize_owner_whatsapp_settings(settings_doc: dict | None, tenant: dict | None = None) -> dict:
    data = serialize_whatsapp_settings(settings_doc, tenant)
    data["bridgeToken"] = (settings_doc or {}).get("bridgeToken", "")
    data["bridgeStatus"] = (settings_doc or {}).get("bridgeStatus", "")
    data["bridgeConnectedNumber"] = (settings_doc or {}).get("bridgeConnectedNumber", "")
    data["bridgeLastSeenAt"] = (settings_doc or {}).get("bridgeLastSeenAt")
    data["bridgeLastError"] = (settings_doc or {}).get("bridgeLastError", "")
    return data


async def get_customer_facing_whatsapp_agent(tenant: dict) -> dict:
    """Return safe WhatsApp contact details for public/customer pages."""
    db = get_database()
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant["_id"], "isConnected": True})
    contact = tenant.get("contact") or {}
    enabled_modules = set(tenant.get("enabledModuleCodes") or [])
    business_number = (integration or {}).get("businessWhatsAppNumber") or contact.get("whatsapp") or ""
    normalized_number = normalize_phone(business_number)
    agent_enabled = bool((integration or {}).get("agentEnabled", True)) if integration else False
    auto_reply_enabled = bool((integration or {}).get("autoReplyEnabled", True)) if integration else False
    module_ready = "whatsapp_agent" in enabled_modules
    enabled = bool(normalized_number and module_ready)
    default_text = "Hello, I found your business on BizXusAI and I want to ask about your products."
    return {
        "enabled": enabled,
        "configured": bool(integration or normalized_number),
        "status": (integration or {}).get("status", "contact_only" if normalized_number else "not_configured"),
        "provider": (integration or {}).get("provider", settings.whatsapp_provider),
        "agentReady": bool(integration and module_ready and agent_enabled and auto_reply_enabled),
        "displayName": (integration or {}).get("displayName") or tenant.get("name", ""),
        "businessWhatsAppNumber": business_number,
        "normalizedBusinessWhatsAppNumber": normalized_number,
        "waLink": build_whatsapp_deep_link(normalized_number, default_text),
        "autoReplyEnabled": auto_reply_enabled,
        "agentEnabled": agent_enabled,
        "messageHint": (
            "Message this business on WhatsApp. If the owner bridge is running, BizXusAI AI can reply from this number."
            if normalized_number
            else "This business has not added a WhatsApp number yet."
        ),
    }


async def _get_tenant_for_whatsapp_owner(tenant_id: str, user: dict) -> tuple[ObjectId, dict]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "whatsapp_agent")
    await ensure_tenant_module_enabled(tenant_oid, "ai_chat")
    return tenant_oid, tenant


async def get_whatsapp_settings_for_owner(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    settings_doc = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    return {"tenant": serialize_document(tenant), "settings": _serialize_owner_whatsapp_settings(settings_doc, tenant)}


async def upsert_whatsapp_settings(tenant_id: str, payload: WhatsAppSettingsRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    now = datetime.now(timezone.utc)
    business_number = normalize_phone(payload.businessWhatsAppNumber)
    existing_doc = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid}) or {}
    provider = str(payload.provider or "mock").strip().lower()
    if provider not in {"mock", "baileys"}:
        provider = "mock"
    update_doc = {
        "tenantId": tenant_oid,
        "provider": provider,
        "businessWhatsAppNumber": business_number,
        "normalizedBusinessWhatsAppNumber": business_number,
        "displayName": payload.displayName.strip() or tenant.get("name", ""),
        "webhookVerifyToken": settings.whatsapp_verify_token,
        "bridgeToken": existing_doc.get("bridgeToken") or secrets.token_urlsafe(32),
        "isConnected": bool(business_number),
        "agentEnabled": payload.agentEnabled,
        "autoReplyEnabled": payload.autoReplyEnabled,
        "handoffEnabled": payload.handoffEnabled,
        "handoffKeywords": payload.handoffKeywords or DEFAULT_HANDOFF_KEYWORDS,
        "welcomeMessage": payload.welcomeMessage,
        "fallbackReply": payload.fallbackReply,
        "businessHoursMode": payload.businessHoursMode,
        "status": f"connected_{provider}" if business_number else "needs_phone",
        "updatedAt": now,
    }
    await db.whatsapp_integrations.update_one(
        {"tenantId": tenant_oid},
        {"$set": update_doc, "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )
    settings_doc = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    return {"tenant": serialize_document(tenant), "settings": _serialize_owner_whatsapp_settings(settings_doc, tenant)}


async def disconnect_whatsapp_settings(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    now = datetime.now(timezone.utc)
    await db.whatsapp_integrations.update_one(
        {"tenantId": tenant_oid},
        {
            "$set": {
                "isConnected": False,
                "status": "disconnected",
                "agentEnabled": False,
                "autoReplyEnabled": False,
                "updatedAt": now,
            }
        },
    )
    settings_doc = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    return {"tenant": serialize_document(tenant), "settings": _serialize_owner_whatsapp_settings(settings_doc, tenant)}


async def refresh_whatsapp_bridge_token(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    now = datetime.now(timezone.utc)
    await db.whatsapp_integrations.update_one(
        {"tenantId": tenant_oid},
        {"$set": {"bridgeToken": secrets.token_urlsafe(32), "updatedAt": now}},
        upsert=False,
    )
    settings_doc = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    if not settings_doc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save WhatsApp settings before creating a bridge token.")
    return {"tenant": serialize_document(tenant), "settings": _serialize_owner_whatsapp_settings(settings_doc, tenant)}


def _needs_handoff(message_text: str, integration: dict) -> bool:
    if not integration.get("handoffEnabled", True):
        return False
    text = str(message_text or "").lower()
    return any(keyword in text for keyword in integration.get("handoffKeywords") or DEFAULT_HANDOFF_KEYWORDS)


async def _log_inbound_message(
    *,
    tenant_id: ObjectId,
    conversation_id: ObjectId,
    customer_phone: str,
    message_text: str,
    provider: str = "mock",
    provider_message_id: str = "",
    raw_payload: dict | None = None,
) -> None:
    db = get_database()
    now = datetime.now(timezone.utc)
    await db.whatsapp_message_logs.insert_one(
        {
            "tenantId": tenant_id,
            "conversationId": conversation_id,
            "provider": provider,
            "direction": "inbound",
            "fromPhone": normalize_phone(customer_phone),
            "messageText": message_text,
            "providerMessageId": provider_message_id,
            "deliveryStatus": "received",
            "rawPayload": raw_payload or {},
            "createdAt": now,
            "updatedAt": now,
        }
    )


async def _create_whatsapp_owner_notification(
    tenant_id: ObjectId,
    notification_type: str,
    title: str,
    message: str,
    *,
    priority: str = "normal",
    metadata: dict | None = None,
    source_key: str = "",
) -> None:
    try:
        await create_business_notification(
            tenant_id,
            notification_type,
            title,
            message,
            priority=priority,
            metadata=metadata or {},
            source_key=source_key,
        )
    except Exception as exc:
        # A failed alert must not break the customer reply, but it must not vanish either:
        # handoff requests and agent errors are exactly what an owner needs to see.
        logger.warning("Could not create WhatsApp owner notification (%s): %s", notification_type, exc)
        return


async def _get_or_create_conversation(db, tenant: dict, customer_phone: str, customer_name: str) -> dict:
    normalized_phone = normalize_phone(customer_phone)
    now = datetime.now(timezone.utc)
    conversation = await db.conversations.find_one(
        {
            "tenantId": tenant["_id"],
            "channel": "whatsapp",
            "externalCustomerPhone": normalized_phone,
            "status": {"$ne": "closed"},
        },
        sort=[("lastMessageAt", -1)],
    )
    if conversation:
        return conversation
    conversation_doc = {
        "tenantId": tenant["_id"],
        "customerUserId": None,
        "channel": "whatsapp",
        "externalCustomerPhone": normalized_phone,
        "externalCustomerName": customer_name or "WhatsApp Customer",
        "title": f"WhatsApp - {customer_name or normalized_phone}",
        "status": "active",
        "languageDetected": "mixed",
        "lastMessageAt": now,
        "createdAt": now,
        "updatedAt": now,
    }
    conversation_doc["_id"] = (await db.conversations.insert_one(conversation_doc)).inserted_id
    return conversation_doc


async def process_whatsapp_inbound(
    *,
    integration: dict,
    tenant: dict,
    customer_phone: str,
    customer_name: str,
    message_text: str,
    provider_message_id: str = "",
    raw_payload: dict | None = None,
) -> dict:
    db = get_database()
    conversation = await _get_or_create_conversation(db, tenant, customer_phone, customer_name)
    if provider_message_id:
        existing_log = await db.whatsapp_message_logs.find_one(
            {
                "tenantId": tenant["_id"],
                "direction": "inbound",
                "providerMessageId": provider_message_id,
            }
        )
        if existing_log:
            messages = await load_conversation_messages(conversation["_id"])
            return {
                "tenant": serialize_document(tenant),
                "settings": serialize_whatsapp_settings(integration, tenant),
                "conversation": serialize_document(conversation),
                "messages": messages,
                "reply": "",
                "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
                "outboundLog": None,
                "outboundError": "",
                "duplicate": True,
                "handoffRequired": conversation.get("status") == "handoff",
            }

    inbound_received_at = datetime.now(timezone.utc)
    await _log_inbound_message(
        tenant_id=tenant["_id"],
        conversation_id=conversation["_id"],
        customer_phone=customer_phone,
        message_text=message_text,
        provider=integration.get("provider", "mock"),
        provider_message_id=provider_message_id,
        raw_payload=raw_payload,
    )

    language_mode = detect_language_mode(message_text)
    await save_message(conversation, tenant["_id"], "customer", message_text, intent="whatsapp_inbound", confidence=1.0)
    recent_messages = await load_conversation_messages(conversation["_id"])

    if _needs_handoff(message_text, integration):
        ai_text = HANDOFF_REPLY
        draft_order = {}
        rag_sources = []
        tool_calls = [{"tool": "handoff_detector", "handoffRequested": True}]
        reply_meta = {"intent": "handoff_requested", "confidence": 1.0, "responseSource": "handoff_rule", "knowledgeCount": 0, "localizationScore": 1.0}
        await db.conversations.update_one({"_id": conversation["_id"]}, {"$set": {"status": "handoff", "handoffRequestedAt": inbound_received_at}})
        await _create_whatsapp_owner_notification(
            tenant["_id"],
            "whatsapp_handoff",
            "WhatsApp handoff requested",
            f"{customer_name or normalize_phone(customer_phone)} asked for a human reply on WhatsApp.",
            priority="high",
            metadata={"conversationId": str(conversation["_id"]), "customerPhone": normalize_phone(customer_phone), "messageText": message_text},
            source_key=f"whatsapp_handoff:{conversation['_id']}",
        )
    elif not integration.get("agentEnabled", True):
        ai_text = integration.get("fallbackReply") or "Your WhatsApp message has been received. The business team will reply soon."
        draft_order = {}
        rag_sources = []
        tool_calls = [{"tool": "agent_gate", "agentEnabled": False}]
        reply_meta = {"intent": "agent_disabled", "confidence": 1.0, "responseSource": "agent_disabled_rule", "knowledgeCount": 0, "localizationScore": 1.0}
    elif integration.get("autoReplyEnabled", True):
        try:
            ai_text, draft_order, rag_sources, tool_calls, reply_meta = await build_ai_reply(tenant, message_text, recent_messages, channel="whatsapp")
        except Exception as exc:
            ai_text = integration.get("fallbackReply") or DEFAULT_FALLBACK_REPLY
            draft_order = {}
            rag_sources = []
            tool_calls = [{"tool": "agent_error_guard", "error": type(exc).__name__}]
            reply_meta = {"intent": "agent_error", "confidence": 1.0, "responseSource": "agent_error_guard", "knowledgeCount": 0, "localizationScore": 0}
            await _create_whatsapp_owner_notification(
                tenant["_id"],
                "whatsapp_agent_error",
                "WhatsApp AI needs review",
                f"The WhatsApp agent could not answer {customer_name or normalize_phone(customer_phone)} automatically.",
                priority="high",
                metadata={"conversationId": str(conversation["_id"]), "customerPhone": normalize_phone(customer_phone), "messageText": message_text, "errorType": type(exc).__name__, "error": str(exc)[:500]},
            )
    else:
        ai_text = integration.get("welcomeMessage") or "Your message has been received. The business team will reply soon."
        draft_order = {}
        rag_sources = []
        tool_calls = [{"tool": "auto_reply_gate", "autoReplyEnabled": False}]
        reply_meta = {"intent": "manual_review", "confidence": 1.0, "responseSource": "manual_review_rule", "knowledgeCount": 0, "localizationScore": 1.0}

    now = datetime.now(timezone.utc)
    await db.conversations.update_one(
        {"_id": conversation["_id"]},
        {
            "$set": {
                "languageDetected": language_mode,
                "pendingOrderDraft": draft_order,
                "summary": ai_text,
                "lastIntent": reply_meta["intent"],
                "lastIntentConfidence": reply_meta["confidence"],
                "lastAssistantSource": reply_meta["responseSource"],
                "lastKnowledgeCount": reply_meta["knowledgeCount"],
                "lastLocalizationScore": reply_meta.get("localizationScore", 0),
                "lastMessageAt": now,
                "lastInboundAt": inbound_received_at,
                "updatedAt": now,
            }
        },
    )
    conversation = await db.conversations.find_one({"_id": conversation["_id"]})
    await save_message(conversation, tenant["_id"], "ai", ai_text, intent=reply_meta["intent"], confidence=reply_meta["confidence"], rag_sources=rag_sources, tool_calls=tool_calls)

    outbound_log = None
    outbound_error = ""
    if integration.get("autoReplyEnabled", True):
        try:
            outbound_log = await send_whatsapp_text(
                tenant_id=tenant["_id"],
                conversation_id=conversation["_id"],
                provider=integration.get("provider", "mock"),
                to_phone=normalize_phone(customer_phone),
                message_text=ai_text,
                integration=integration,
                raw_context={"source": "whatsapp_agent_auto_reply"},
            )
            await db.whatsapp_integrations.update_one(
                {"_id": integration["_id"]},
                {"$set": {"lastInboundAt": inbound_received_at, "lastOutboundAt": now, "lastWebhookStatus": "processed", "updatedAt": now}},
            )
        except WhatsAppSendError as exc:
            outbound_error = str(exc)
            await db.whatsapp_integrations.update_one(
                {"_id": integration["_id"]},
                {"$set": {"lastInboundAt": inbound_received_at, "lastWebhookStatus": "processed", "lastError": outbound_error, "updatedAt": now}},
            )

    messages = await load_conversation_messages(conversation["_id"])
    return {
        "tenant": serialize_document(tenant),
        "settings": serialize_whatsapp_settings(integration, tenant),
        "conversation": serialize_document(conversation),
        "messages": messages,
        "reply": ai_text,
        "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
        "outboundLog": serialize_document(outbound_log) if outbound_log else None,
        "outboundError": outbound_error,
        "duplicate": False,
        "handoffRequired": conversation.get("status") == "handoff",
    }


async def simulate_whatsapp_inbound(tenant_id: str, payload: WhatsAppMockInboundRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid, "isConnected": True})
    if not integration:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connect WhatsApp before testing inbound messages.")
    return await process_whatsapp_inbound(
        integration=integration,
        tenant=tenant,
        customer_phone=payload.customerPhone,
        customer_name=payload.customerName,
        message_text=payload.messageText,
        provider_message_id=payload.providerMessageId or f"mock-in-{int(datetime.now(timezone.utc).timestamp())}",
        raw_payload={"mock": True, "source": "dashboard_simulator"},
    )


async def send_owner_whatsapp_test(tenant_id: str, payload: WhatsAppOutboundRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid, "isConnected": True})
    if not integration:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connect WhatsApp before sending a test message.")
    try:
        log = await send_whatsapp_text(
            tenant_id=tenant_oid,
            provider=integration.get("provider", "mock"),
            to_phone=normalize_phone(payload.toPhone),
            message_text=payload.messageText,
            integration=integration,
            raw_context={"source": "owner_test_message"},
        )
    except WhatsAppSendError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unable to send WhatsApp test: {exc}") from exc
    return {"tenant": serialize_document(tenant), "log": serialize_document(log)}


async def process_bridge_status(payload: WhatsAppBridgeStatusRequest, bridge_token: str) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(payload.tenantId, "tenantId")
    integration = await db.whatsapp_integrations.find_one(
        {"tenantId": tenant_oid, "bridgeToken": bridge_token, "provider": "baileys", "isConnected": True}
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WhatsApp bridge token or tenant.")

    now = datetime.now(timezone.utc)
    connected_number = normalize_phone(payload.connectedNumber)
    update_doc = {
        "bridgeStatus": payload.status,
        "bridgeConnectedNumber": connected_number,
        "bridgeLastSeenAt": now,
        "bridgeLastError": payload.lastError,
        "updatedAt": now,
    }
    if connected_number:
        update_doc["businessWhatsAppNumber"] = connected_number
        update_doc["normalizedBusinessWhatsAppNumber"] = connected_number
        update_doc["status"] = "connected_baileys"
    elif payload.status in {"logged_out", "connection_failed"}:
        update_doc["status"] = payload.status

    await db.whatsapp_integrations.update_one({"_id": integration["_id"]}, {"$set": update_doc})
    integration = await db.whatsapp_integrations.find_one({"_id": integration["_id"]})
    tenant = await db.tenants.find_one({"_id": tenant_oid}) or {}
    return {"tenant": serialize_document(tenant), "settings": _serialize_owner_whatsapp_settings(integration, tenant)}


async def process_bridge_inbound(payload: WhatsAppBridgeInboundRequest, bridge_token: str) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(payload.tenantId, "tenantId")
    integration = await db.whatsapp_integrations.find_one(
        {"tenantId": tenant_oid, "bridgeToken": bridge_token, "provider": "baileys", "isConnected": True}
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WhatsApp bridge token or tenant.")
    if not integration.get("agentEnabled", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="WhatsApp agent is disabled for this business.")

    tenant = await db.tenants.find_one({"_id": tenant_oid})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found for WhatsApp bridge.")

    now = datetime.now(timezone.utc)
    connected_number = normalize_phone(payload.connectedNumber)
    if connected_number:
        await db.whatsapp_integrations.update_one(
            {"_id": integration["_id"]},
            {
                "$set": {
                    "bridgeStatus": "ready",
                    "bridgeConnectedNumber": connected_number,
                    "bridgeLastSeenAt": now,
                    "businessWhatsAppNumber": connected_number,
                    "normalizedBusinessWhatsAppNumber": connected_number,
                    "lastInboundAt": now,
                    "updatedAt": now,
                }
            },
        )
        integration = await db.whatsapp_integrations.find_one({"_id": integration["_id"]}) or integration

    data = await process_whatsapp_inbound(
        integration=integration,
        tenant=tenant,
        customer_phone=payload.customerPhone,
        customer_name=payload.customerName,
        message_text=payload.messageText,
        provider_message_id=payload.providerMessageId,
        raw_payload={"source": "baileys_bridge", **(payload.rawPayload or {})},
    )
    return data


async def list_whatsapp_conversations(tenant_id: str, user: dict, page: int = 1, limit: int = 20) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    query = {"tenantId": tenant_oid, "channel": "whatsapp"}
    total = await db.conversations.count_documents(query)
    cursor = db.conversations.find(query).sort("lastMessageAt", -1).skip((page - 1) * limit).limit(limit)
    items = [serialize_document(conversation) async for conversation in cursor]
    return {
        "tenant": serialize_document(tenant),
        "items": items,
        "pagination": {"page": page, "limit": limit, "total": total, "totalPages": (total + limit - 1) // limit},
    }
