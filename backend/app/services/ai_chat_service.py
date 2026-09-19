import logging
import secrets
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo import ReturnDocument

from app.ai.agents.actions import checkout_readiness
from app.ai.agents.basket import resolve_basket
from app.ai.agents.orchestrator_agent import run_customer_agent
from app.ai.agents.tools import detect_language_mode  # re-exported: single source of truth for language detection
from app.core.module_guard import ensure_tenant_ai_budget, ensure_tenant_module_enabled, ensure_tenant_module_usage_available
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.customer_portal_common_service import get_customer_profile_and_user, get_marketplace_tenant_or_404
from app.services.payment_service import get_customer_payment_options_for_tenant

logger = logging.getLogger(__name__)

__all__ = ["detect_language_mode", "save_message", "load_conversation_messages", "build_ai_reply", "build_ai_turn", "get_customer_chat_state", "send_customer_chat_message", "clear_customer_conversation_draft", "get_public_chat_state", "send_public_chat_message", "list_owner_conversations", "get_owner_conversation_detail"]


async def _serialize_chat_tenant(tenant: dict) -> dict:
    serialized = serialize_document(tenant)
    # This serializer also answers anonymous website chat, so it advertises the
    # guest-safe set. A signed-in customer still sees the code flow on the order page,
    # where the account behind the checkout is known.
    serialized["paymentOptions"] = await get_customer_payment_options_for_tenant(tenant["_id"], allow_otp=False)
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
    """Build an AI reply through the agent tool layer.

    The five-value return shape is kept for callers that only want a reply. Anything
    that also needs the basket calls :func:`build_ai_turn` instead.
    """
    result = await build_ai_turn(tenant, user_message, recent_messages, channel=channel)
    return (
        result["reply"],
        result["draftOrder"],
        result["ragSources"],
        result["toolCalls"],
        result["meta"],
    )


async def _claim_pending_basket_confirmation(conversation: dict | None) -> dict:
    """Take the outstanding cart proposal, so that only one turn can act on it.

    Reading it and writing it back at the end of the turn is check-then-act, and this is
    the one piece of conversation state a "yes" turns into a real cart change. Two
    requests arriving together - a double-tap, a client retry, a WhatsApp webhook
    redelivery - both read the same proposal and both applied it, so one "shall I add 2 x
    Zinger Burger?" produced four. A turn that raised after the customer message was
    saved left the proposal armed, and the retry applied it a second time.

    So it is claimed the way `pendingOrderDraft` already is: whoever wins the atomic
    update owns it, everyone else sees nothing outstanding and simply re-reads the
    message. The turn writes the new state back when it finishes, which is also what
    restores a proposal that is being carried rather than answered.
    """
    conversation_id = (conversation or {}).get("_id")
    if not conversation_id:
        return {}
    stored = (conversation or {}).get("pendingBasketConfirmation") or {}
    if not stored.get("actions"):
        # Nothing to race over. `awaitingDetails` is advisory and read-only here.
        return stored
    db = get_database()
    claimed = await db.conversations.find_one_and_update(
        {"_id": conversation_id, "pendingBasketConfirmation.actions.0": {"$exists": True}},
        {"$set": {"pendingBasketConfirmation": {"awaitingDetails": stored.get("awaitingDetails") or []}}},
        return_document=ReturnDocument.BEFORE,
    )
    if not claimed:
        # Another request got there first.
        return {"awaitingDetails": stored.get("awaitingDetails") or []}
    return claimed.get("pendingBasketConfirmation") or {}


async def _restore_pending_basket_confirmation(conversation: dict | None, pending: dict) -> None:
    """Undo a claim whose turn never finished.

    Only restores what was actually claimed, and only over a slot nothing else has taken
    in the meantime, so a concurrent turn that legitimately stored a new proposal wins.
    """
    conversation_id = (conversation or {}).get("_id")
    if not conversation_id or not (pending or {}).get("actions"):
        return
    try:
        await get_database().conversations.update_one(
            {"_id": conversation_id, "pendingBasketConfirmation.actions.0": {"$exists": False}},
            {"$set": {"pendingBasketConfirmation": pending}},
        )
    except Exception:
        logger.exception("Could not restore the pending basket confirmation after a failed turn.")


async def build_ai_turn(
    tenant: dict,
    user_message: str,
    recent_messages: list[dict],
    *,
    channel: str = "customer_portal",
    customer_user: dict | None = None,
    conversation: dict | None = None,
    phone: str = "",
) -> dict:
    """Run one turn, with a basket when this conversation can have one.

    Which basket - the customer's real cart or a draft on the conversation - is decided
    by ``resolve_basket`` from the identity available on this channel, never by the
    caller. An owner preview has neither, and simply runs without a basket.
    """
    basket = await resolve_basket(
        tenant,
        channel=channel,
        customer_user=customer_user,
        conversation_id=(conversation or {}).get("_id"),
        phone=phone,
    )
    pending = await _claim_pending_basket_confirmation(conversation)
    outcome: dict = {}
    try:
        return await run_customer_agent(
            tenant,
            user_message,
            recent_messages,
            channel=channel,
            basket=basket,
            pending_confirmation=pending,
            outcome=outcome,
        )
    except Exception:
        # The claim is a lock, not a consumption. If the turn dies the customer gets no
        # reply, and destroying their outstanding question as well would mean their "yes"
        # vanished with nothing to show for it: the transcript keeps the message, the
        # retry finds nothing to answer, and they are never told. Put it back.
        #
        # UNLESS the cart was already written. The turn does several more things after
        # applying a confirmed proposal, and any of them can raise; restoring the proposal
        # then re-arms an action that has already happened, and the retry applies it a
        # second time. That is the double-apply this claim exists to prevent, so a turn
        # that got as far as the cart keeps its claim consumed.
        if not outcome.get("basketApplied"):
            await _restore_pending_basket_confirmation(conversation, pending)
        raise


async def basket_snapshot(
    tenant: dict,
    *,
    channel: str,
    customer_user: dict | None = None,
    conversation: dict | None = None,
    phone: str = "",
) -> dict:
    """Read the basket without running the agent.

    Used by the GET chat endpoints, which restore a conversation rather than advancing
    it, so the panel shows the current basket on page load.
    """
    basket = await resolve_basket(
        tenant,
        channel=channel,
        customer_user=customer_user,
        conversation_id=(conversation or {}).get("_id"),
        phone=phone,
    )
    if basket is None:
        return {"basket": {}, "checkoutDraft": {}, "checkoutReadiness": {}}

    summary = await basket.summary()
    draft = await basket.get_checkout_draft()
    allowed_fulfillment = (
        ((tenant.get("settings") or {}).get("categoryHints") or {}).get("fulfillment") or {}
    ).get("allowedTypes") or ["none", "pickup", "delivery"]
    return {
        "basket": summary,
        "checkoutDraft": draft,
        "checkoutReadiness": checkout_readiness(
            summary,
            draft,
            has_account=bool(basket.identity.customerUserId),
            allowed_fulfillment_types=allowed_fulfillment,
        ),
    }


async def get_customer_chat_state(slug: str, current_user: dict) -> dict:
    tenant = await get_marketplace_tenant_or_404(slug)
    if "ai_chat" not in tenant.get("enabledModuleCodes", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI chat is disabled for this business.")

    conversation = await get_or_create_customer_conversation(tenant, current_user)
    messages = await load_conversation_messages(conversation["_id"])
    snapshot = await basket_snapshot(
        tenant, channel="customer_portal", customer_user=current_user, conversation=conversation
    )
    return {
        "tenant": await _serialize_chat_tenant(tenant),
        "conversation": serialize_document(conversation),
        "messages": messages,
        "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
        **snapshot,
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
    turn = await build_ai_turn(
        tenant,
        message_text,
        recent_messages,
        channel="customer_portal",
        customer_user=current_user,
        conversation=conversation,
    )
    ai_text = turn["reply"]
    draft_order = turn["draftOrder"]
    rag_sources = turn["ragSources"]
    tool_calls = turn["toolCalls"]
    reply_meta = turn["meta"]

    now = datetime.now(timezone.utc)
    await db.conversations.update_one(
        {"_id": conversation["_id"]},
        {
            "$set": {
                "languageDetected": language_mode,
                "pendingOrderDraft": draft_order,
                # An unanswered "shall I clear your cart?" has to survive to the next
                # message, or "yes" arrives with nothing to attach itself to.
                "pendingBasketConfirmation": turn.get("pendingConfirmation") or {},
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
        "basket": turn.get("basket") or {},
        "checkoutDraft": turn.get("checkoutDraft") or {},
        "checkoutReadiness": turn.get("checkoutReadiness") or {},
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
        **(await basket_snapshot(tenant, channel="website", conversation=conversation)),
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
    turn = await build_ai_turn(
        tenant,
        message_text,
        recent_messages,
        channel="website",
        conversation=conversation,
    )
    ai_text = turn["reply"]
    draft_order = turn["draftOrder"]
    rag_sources = turn["ragSources"]
    tool_calls = turn["toolCalls"]
    reply_meta = turn["meta"]
    now = datetime.now(timezone.utc)
    await db.conversations.update_one(
        {"_id": conversation["_id"]},
        {
            "$set": {
                "languageDetected": language_mode,
                "pendingOrderDraft": draft_order,
                # Without this the website chat forgets that it asked "are you sure?",
                # so a "yes" re-plans the original message and asks again forever.
                "pendingBasketConfirmation": turn.get("pendingConfirmation") or {},
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
        "basket": turn.get("basket") or {},
        "checkoutDraft": turn.get("checkoutDraft") or {},
        "checkoutReadiness": turn.get("checkoutReadiness") or {},
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
