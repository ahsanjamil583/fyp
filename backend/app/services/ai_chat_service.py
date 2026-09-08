import secrets
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.ai.agents.orchestrator_agent import run_customer_agent
from app.ai.agents.tools import detect_language_mode  # re-exported: single source of truth for language detection
from app.core.module_guard import ensure_tenant_ai_budget, ensure_tenant_module_enabled, ensure_tenant_module_usage_available
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.customer_portal_common_service import get_customer_profile_and_user, get_marketplace_tenant_or_404
from app.services.payment_service import get_customer_payment_options_for_tenant

__all__ = ["detect_language_mode", "save_message", "load_conversation_messages", "build_ai_reply", "get_customer_chat_state", "send_customer_chat_message", "clear_customer_conversation_draft", "get_public_chat_state", "send_public_chat_message", "list_owner_conversations", "get_owner_conversation_detail"]


async def _serialize_chat_tenant(tenant: dict) -> dict:
    serialized = serialize_document(tenant)
    serialized["paymentOptions"] = await get_customer_payment_options_for_tenant(tenant["_id"])
    return serialized


async def save_message(
    conversation: dict,
    tenant_id: ObjectId,
    sender: str,
    message_text: str,
    intent: str = "",
    confidence: float = 0.0,
    rag_sources: list | None = None,
    tool_calls: list | None = None,
) -> dict:
    db = get_database()
    message = {
        "tenantId": tenant_id,
        "conversationId": conversation["_id"],
        "sender": sender,
        "messageText": message_text,
        "intent": intent,
        "confidence": confidence,
        "ragSources": rag_sources or [],
        "toolCalls": tool_calls or [],
        "createdAt": datetime.now(timezone.utc),
    }
    message["_id"] = (await db.messages.insert_one(message)).inserted_id
    return message


async def load_conversation_messages(conversation_id: ObjectId) -> list[dict]:
    db = get_database()
    cursor = db.messages.find({"conversationId": conversation_id}).sort("createdAt", 1).limit(50)
    return [serialize_document(message) async for message in cursor]


async def get_or_create_customer_conversation(tenant: dict, current_user: dict) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    conversation = await db.conversations.find_one(
        {
            "tenantId": tenant["_id"],
            "customerUserId": current_user["_id"],
            "channel": "customer_portal",
            "status": "open",
        }
    )
    if conversation:
        return conversation

    conversation = {
        "tenantId": tenant["_id"],
        "branchId": None,
        "customerId": None,
        "customerUserId": current_user["_id"],
        "channel": "customer_portal",
        "status": "open",
        "languageDetected": "english",
        "pendingOrderDraft": {},
        "summary": "",
        "lastIntent": "",
        "lastIntentConfidence": 0.0,
        "lastAssistantSource": "",
        "lastKnowledgeCount": 0,
        "lastMessageAt": now,
        "createdAt": now,
        "updatedAt": now,
    }
    conversation["_id"] = (await db.conversations.insert_one(conversation)).inserted_id
    return conversation


async def resolve_public_conversation(tenant: dict, session_token: str | None) -> dict | None:
    """Look up a website conversation by its opaque session token.

    Website chat is unauthenticated, so whatever the browser sends back is the only
    credential. A MongoDB ObjectId is a timestamp plus a counter and can be walked,
    which would expose other visitors' transcripts; the token is random instead.
    """
    token = str(session_token or "").strip()
    if not token:
        return None
    return await get_database().conversations.find_one(
        {"publicSessionToken": token, "tenantId": tenant["_id"], "channel": "website"}
    )


def public_conversation_view(conversation: dict | None) -> dict:
    """Serialize a website conversation with its token in place of internal ids."""
    data = serialize_document(conversation) or {}
    if not data:
        return data
    data["id"] = data.pop("publicSessionToken", "")
    data.pop("tenantId", None)
    data.pop("customerUserId", None)
    data.pop("customerId", None)
    return data


async def get_or_create_public_conversation(tenant: dict, conversation_id: str | None = None) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    existing = await resolve_public_conversation(tenant, conversation_id)
    if existing:
        return existing

    conversation = {
        "tenantId": tenant["_id"],
        "branchId": None,
        "customerId": None,
        "customerUserId": None,
        "channel": "website",
        "publicSessionToken": secrets.token_urlsafe(24),
        "status": "open",
        "languageDetected": "english",
        "pendingOrderDraft": {},
        "summary": "",
        "lastIntent": "",
        "lastIntentConfidence": 0.0,
        "lastAssistantSource": "",
        "lastKnowledgeCount": 0,
        "lastMessageAt": now,
        "createdAt": now,
        "updatedAt": now,
    }
    conversation["_id"] = (await db.conversations.insert_one(conversation)).inserted_id
    return conversation


async def get_public_chat_tenant_or_404(slug: str) -> dict:
    db = get_database()
    tenant = await db.tenants.find_one(
        {
            "slug": slug,
            "status": "active",
            "websiteStatus": "published",
            "settings.publicVisibility": True,
        }
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published business not found.")
    return tenant


async def build_ai_reply(tenant: dict, user_message: str, recent_messages: list[dict], channel: str = "customer_portal") -> tuple[str, dict, list[dict], list[dict], dict]:
    """Build an AI reply through the Phase 23 agent tool layer.

    The return shape stays compatible with existing public chat, customer
    portal chat, and WhatsApp code while the implementation now runs a
    real tool/orchestrator pipeline instead of keeping all steps hidden in
    this service.
    """

    result = await run_customer_agent(tenant, user_message, recent_messages, channel=channel)
    return (
        result["reply"],
        result["draftOrder"],
        result["ragSources"],
        result["toolCalls"],
        result["meta"],
    )


async def get_customer_chat_state(slug: str, current_user: dict) -> dict:
    tenant = await get_marketplace_tenant_or_404(slug)
    if "ai_chat" not in tenant.get("enabledModuleCodes", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI chat is disabled for this business.")

    conversation = await get_or_create_customer_conversation(tenant, current_user)
    messages = await load_conversation_messages(conversation["_id"])
    return {
        "tenant": await _serialize_chat_tenant(tenant),
        "conversation": serialize_document(conversation),
        "messages": messages,
        "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
    }


async def send_customer_chat_message(slug: str, message_text: str, current_user: dict) -> dict:
    db = get_database()
    await get_customer_profile_and_user(current_user)
    tenant = await get_marketplace_tenant_or_404(slug)
    if "ai_chat" not in tenant.get("enabledModuleCodes", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI chat is disabled for this business.")
    await ensure_tenant_module_usage_available(tenant["_id"], "ai_chat")
    await ensure_tenant_ai_budget(tenant["_id"])

    conversation = await get_or_create_customer_conversation(tenant, current_user)
    language_mode = detect_language_mode(message_text)
    await save_message(conversation, tenant["_id"], "customer", message_text, intent="customer_chat", confidence=1.0)
    recent_messages = await load_conversation_messages(conversation["_id"])
    ai_text, draft_order, rag_sources, tool_calls, reply_meta = await build_ai_reply(tenant, message_text, recent_messages, channel="customer_portal")

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
                "lastLocalizationScore": reply_meta["localizationScore"],
                "lastMessageAt": now,
                "updatedAt": now,
            }
        },
    )
    conversation = await db.conversations.find_one({"_id": conversation["_id"]})
    await save_message(
        conversation,
        tenant["_id"],
        "ai",
        ai_text,
        intent=reply_meta["intent"],
        confidence=reply_meta["confidence"],
        rag_sources=rag_sources,
        tool_calls=tool_calls,
    )
    messages = await load_conversation_messages(conversation["_id"])
    return {
        "tenant": await _serialize_chat_tenant(tenant),
        "conversation": serialize_document(conversation),
        "messages": messages,
        "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
    }


async def clear_customer_conversation_draft(slug: str, conversation_id: str | None, current_user: dict, transaction: dict | None = None) -> None:
    if not conversation_id:
        return
    db = get_database()
    tenant = await get_marketplace_tenant_or_404(slug)
    conversation_oid = parse_object_id(conversation_id, "conversationId")
    conversation = await db.conversations.find_one(
        {"_id": conversation_oid, "tenantId": tenant["_id"], "customerUserId": current_user["_id"], "channel": "customer_portal"}
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    summary = "Draft order confirmed."
    if transaction:
        summary = f"Draft transaction confirmed as {transaction.get('transactionNumber', 'transaction')}."
    now = datetime.now(timezone.utc)
    await db.conversations.update_one(
        {"_id": conversation_oid},
        {"$set": {"pendingOrderDraft": {}, "summary": summary, "lastMessageAt": now, "updatedAt": now}},
    )
    await save_message(conversation, tenant["_id"], "system", summary, intent="draft_confirmed", confidence=1.0)


async def get_public_chat_state(slug: str, conversation_id: str | None = None) -> dict:
    tenant = await get_public_chat_tenant_or_404(slug)
    if "ai_chat" not in tenant.get("enabledModuleCodes", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI chat is disabled for this business.")
    conversation = await get_or_create_public_conversation(tenant, conversation_id)
    messages = await load_conversation_messages(conversation["_id"])
    return {
        "tenant": await _serialize_chat_tenant(tenant),
        "conversation": public_conversation_view(conversation),
        "messages": messages,
        "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
    }


async def send_public_chat_message(slug: str, message_text: str, conversation_id: str | None = None) -> dict:
    db = get_database()
    tenant = await get_public_chat_tenant_or_404(slug)
    if "ai_chat" not in tenant.get("enabledModuleCodes", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI chat is disabled for this business.")
    await ensure_tenant_module_usage_available(tenant["_id"], "ai_chat")
    await ensure_tenant_ai_budget(tenant["_id"])
    conversation = await get_or_create_public_conversation(tenant, conversation_id)
    language_mode = detect_language_mode(message_text)
    await save_message(conversation, tenant["_id"], "customer", message_text, intent="public_chat", confidence=1.0)
    recent_messages = await load_conversation_messages(conversation["_id"])
    ai_text, draft_order, rag_sources, tool_calls, reply_meta = await build_ai_reply(tenant, message_text, recent_messages, channel="website")
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
                "lastLocalizationScore": reply_meta["localizationScore"],
                "lastMessageAt": now,
                "updatedAt": now,
            }
        },
    )
    conversation = await db.conversations.find_one({"_id": conversation["_id"]})
    await save_message(
        conversation,
        tenant["_id"],
        "ai",
        ai_text,
        intent=reply_meta["intent"],
        confidence=reply_meta["confidence"],
        rag_sources=rag_sources,
        tool_calls=tool_calls,
    )
    messages = await load_conversation_messages(conversation["_id"])
    return {
        "tenant": await _serialize_chat_tenant(tenant),
        "conversation": public_conversation_view(conversation),
        "messages": messages,
        "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
    }


async def list_owner_conversations(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "ai_chat")
    cursor = db.conversations.find({"tenantId": tenant_oid}).sort("lastMessageAt", -1).limit(50)
    conversations = [serialize_document(conversation) async for conversation in cursor]
    return {"tenant": serialize_document(tenant), "items": conversations}


async def get_owner_conversation_detail(tenant_id: str, conversation_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "ai_chat")
    conversation_oid = parse_object_id(conversation_id, "conversationId")
    conversation = await db.conversations.find_one({"_id": conversation_oid, "tenantId": tenant_oid})
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    messages = await load_conversation_messages(conversation_oid)
    return {"tenant": serialize_document(tenant), "conversation": serialize_document(conversation), "messages": messages}
