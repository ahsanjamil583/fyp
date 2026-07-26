import re
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.db.mongodb import get_database
from app.services.customer_portal_common_service import get_customer_profile_and_user, get_marketplace_tenant_or_404


def _detect_language_mode(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["hai", "mujhe", "chahiye", "krdo", "kar do", "order", "please"]):
        return "mixed"
    return "english"


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1}


def _score_item_match(message_text: str, item: dict) -> int:
    text = message_text.lower()
    name = str(item.get("name", "")).lower()
    description = str(item.get("description", "")).lower()
    tags = " ".join(item.get("tags", [])).lower()

    if name and name in text:
        return 100 + len(name)

    item_tokens = _tokenize(f"{name} {description} {tags}")
    message_tokens = _tokenize(text)
    return len(item_tokens.intersection(message_tokens))


def _extract_quantity(message_text: str, item_name: str) -> int:
    text = message_text.lower()
    normalized_item_name = item_name.lower()
    patterns = [
        rf"(\d+)\s+(?:x\s+)?{re.escape(normalized_item_name)}",
        rf"{re.escape(normalized_item_name)}\s+(?:x\s+)?(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return max(1, min(int(match.group(1)), 99))
    return 1


async def _get_or_create_customer_conversation(tenant: dict, current_user: dict) -> dict:
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
        "lastMessageAt": now,
        "createdAt": now,
        "updatedAt": now,
    }
    conversation["_id"] = (await db.conversations.insert_one(conversation)).inserted_id
    return conversation


async def _save_message(conversation: dict, tenant_id, sender: str, message_text: str, intent: str = "", confidence: float = 0.0, tool_calls: list | None = None) -> dict:
    db = get_database()
    message = {
        "tenantId": tenant_id,
        "conversationId": conversation["_id"],
        "sender": sender,
        "messageText": message_text,
        "intent": intent,
        "confidence": confidence,
        "ragSources": [],
        "toolCalls": tool_calls or [],
        "createdAt": datetime.now(timezone.utc),
    }
    message["_id"] = (await db.messages.insert_one(message)).inserted_id
    return message


async def _load_conversation_messages(conversation_id) -> list[dict]:
    db = get_database()
    cursor = db.messages.find({"conversationId": conversation_id}).sort("createdAt", 1).limit(50)
    return [serialize_document(message) async for message in cursor]


async def get_customer_chat_state(slug: str, current_user: dict) -> dict:
    tenant = await get_marketplace_tenant_or_404(slug)
    if "ai_chat" not in tenant.get("enabledModuleCodes", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI chat is disabled for this business.")

    conversation = await _get_or_create_customer_conversation(tenant, current_user)
    messages = await _load_conversation_messages(conversation["_id"])
    return {
        "tenant": serialize_document(tenant),
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

    conversation = await _get_or_create_customer_conversation(tenant, current_user)
    await _save_message(conversation, tenant["_id"], "customer", message_text, intent="order_request", confidence=1.0)

    items = await db.items.find(
        {
            "tenantId": tenant["_id"],
            "status": "active",
            "$or": [{"isSellable": True}, {"isBookable": True}],
        }
    ).to_list(length=100)

    ranked_items = sorted(
        [
            (item, _score_item_match(message_text, item))
            for item in items
        ],
        key=lambda row: row[1],
        reverse=True,
    )
    matched_items = [row[0] for row in ranked_items if row[1] > 0][:3]
    now = datetime.now(timezone.utc)

    draft_order = {}
    if matched_items:
        primary_item = matched_items[0]
        quantity = _extract_quantity(message_text, primary_item.get("name", ""))
        draft_order = {
            "conversationId": conversation["_id"],
            "tenantId": tenant["_id"],
            "items": [
                {
                    "itemId": primary_item["_id"],
                    "name": primary_item.get("name", ""),
                    "quantity": quantity,
                    "unitPrice": float(primary_item.get("price", 0)),
                    "currency": primary_item.get("currency", "PKR"),
                }
            ],
            "suggestedItems": [
                {
                    "itemId": item["_id"],
                    "name": item.get("name", ""),
                    "price": float(item.get("price", 0)),
                    "currency": item.get("currency", "PKR"),
                }
                for item in matched_items
            ],
            "status": "awaiting_confirmation",
            "source": "rule_based",
            "suggestedAt": now,
        }
        ai_text = (
            f"I found {primary_item.get('name', 'an item')} for you. "
            f"I prepared a draft with quantity {quantity}. "
            "Please confirm the draft order below to place it."
        )
    else:
        ai_text = (
            "I could not match that request to an available item yet. "
            "Please mention the product or service name, for example: order 2 zinger burgers."
        )

    conversation_update = {
        "languageDetected": _detect_language_mode(message_text),
        "pendingOrderDraft": draft_order,
        "summary": ai_text,
        "lastMessageAt": now,
        "updatedAt": now,
    }
    await db.conversations.update_one({"_id": conversation["_id"]}, {"$set": conversation_update})
    conversation = await db.conversations.find_one({"_id": conversation["_id"]})

    await _save_message(
        conversation,
        tenant["_id"],
        "ai",
        ai_text,
        intent="draft_order_suggestion" if matched_items else "clarification_request",
        confidence=0.85 if matched_items else 0.4,
        tool_calls=[{"tool": "rule_based_item_match", "matchedCount": len(matched_items)}],
    )

    messages = await _load_conversation_messages(conversation["_id"])
    return {
        "tenant": serialize_document(tenant),
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
        {
            "_id": conversation_oid,
            "tenantId": tenant["_id"],
            "customerUserId": current_user["_id"],
            "channel": "customer_portal",
        }
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    now = datetime.now(timezone.utc)
    summary = "Draft order confirmed."
    if transaction:
        summary = f"Draft transaction confirmed as {transaction.get('transactionNumber', 'transaction')}."

    await db.conversations.update_one(
        {"_id": conversation_oid},
        {
            "$set": {
                "pendingOrderDraft": {},
                "summary": summary,
                "lastMessageAt": now,
                "updatedAt": now,
            }
        },
    )
    await _save_message(
        conversation,
        tenant["_id"],
        "system",
        summary,
        intent="draft_confirmed",
        confidence=1.0,
    )
