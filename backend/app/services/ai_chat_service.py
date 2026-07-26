import re
from datetime import datetime, timezone

import httpx

from app.ai.agents.orchestrator_agent import run_customer_agent
from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.module_guard import ensure_tenant_module_enabled, ensure_tenant_module_usage_available
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.customer_portal_common_service import get_customer_profile_and_user, get_marketplace_tenant_or_404
from app.services.localization_service import build_ai_localization_guidance, evaluate_localized_reply, get_language_mode
from app.services.payment_service import get_customer_payment_options_for_tenant
from app.services.rag_index_service import index_tenant_profile_for_rag
from app.services.rag_vector_service import hybrid_retrieve_knowledge

ROMAN_URDU_NUMBER_WORDS = {
    "aik": 1,
    "ak": 1,
    "ek": 1,
    "one": 1,
    "do": 2,
    "two": 2,
    "teen": 3,
    "three": 3,
    "char": 4,
    "chaar": 4,
    "four": 4,
    "panch": 5,
    "paanch": 5,
    "five": 5,
    "cheh": 6,
    "chay": 6,
    "six": 6,
    "saat": 7,
    "sat": 7,
    "seven": 7,
    "aath": 8,
    "eight": 8,
    "nau": 9,
    "nine": 9,
    "das": 10,
    "ten": 10,
}


async def _serialize_chat_tenant(tenant: dict) -> dict:
    serialized = serialize_document(tenant)
    serialized["paymentOptions"] = await get_customer_payment_options_for_tenant(tenant["_id"])
    return serialized

NORMALIZATION_REPLACEMENTS = {
    "krdo": "kar do",
    "kr dena": "kar dena",
    "karna hai": "karna hai",
    "chaiye": "chahiye",
    "chaie": "chahiye",
    "chaye": "chahiye",
    "kitnay": "kitne",
    "kitni": "kitne",
    "keemat": "qeemat",
    "daam": "price",
    "rate": "price",
    "rates": "price",
    "mil jaye ga": "available",
    "mil jayega": "available",
    "milay ga": "available",
    "milta hai": "available",
    "milega": "available",
    "dikhado": "show",
    "dikhao": "show",
    "batao": "tell",
    "mujhay": "mujhe",
    "mai": "main",
    "hun": "hoon",
    "whatsapp": "contact",
    "number": "contact",
    "timing": "hours",
    "timings": "hours",
    "waqt": "hours",
    "location": "address",
    "jagah": "address",
}

ORDER_HINTS = {
    "order",
    "buy",
    "purchase",
    "book",
    "reserve",
    "confirm",
    "deliver",
    "delivery",
    "pickup",
    "pick",
    "cart",
    "chahiye",
    "bhej",
    "send",
}
PRICE_HINTS = {"price", "cost", "qeemat", "charges", "fee", "fees"}
AVAILABILITY_HINTS = {"available", "availability", "stock", "have", "mil", "hai", "open"}
RECOMMENDATION_HINTS = {"suggest", "recommend", "best", "popular", "options", "menu", "show"}
CONTACT_HINTS = {"contact", "phone", "email", "call", "address", "location", "where"}
HOURS_HINTS = {"hours", "timing", "open", "close", "time"}
GREETING_HINTS = {"hi", "hello", "salam", "assalam", "hey", "aoa"}


def normalize_message_text(text: str) -> str:
    normalized = text.lower().strip()
    for old, new in NORMALIZATION_REPLACEMENTS.items():
        normalized = normalized.replace(old, new)
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", normalize_message_text(text)) if len(token) > 1}


def detect_language_mode(text: str) -> str:
    normalized = normalize_message_text(text)
    roman_urdu_hits = sum(
        1
        for token in ["hai", "mujhe", "chahiye", "kar", "qeemat", "kitne", "kya", "kon", "kis", "mil", "acha"]
        if token in normalized.split()
    )
    english_hits = sum(
        1 for token in ["price", "order", "available", "hours", "show", "what", "which", "delivery"] if token in normalized.split()
    )
    if roman_urdu_hits and english_hits:
        return "mixed"
    if roman_urdu_hits:
        return "roman_urdu"
    return "english"


def extract_numeric_quantity(text: str) -> int | None:
    for token in normalize_message_text(text).split():
        if token in ROMAN_URDU_NUMBER_WORDS:
            return ROMAN_URDU_NUMBER_WORDS[token]
    digit_match = re.search(r"\b(\d{1,2})\b", normalize_message_text(text))
    if digit_match:
        return max(1, min(int(digit_match.group(1)), 99))
    return None


def extract_quantity(message_text: str, item_name: str) -> int:
    normalized_text = normalize_message_text(message_text)
    normalized_item_name = normalize_message_text(item_name)
    quantity_value = extract_numeric_quantity(message_text)
    patterns = [
        rf"\b(\d+)\s+(?:x\s+)?{re.escape(normalized_item_name)}\b",
        rf"\b{re.escape(normalized_item_name)}\s+(?:x\s+)?(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized_text)
        if match:
            return max(1, min(int(match.group(1)), 99))
    return quantity_value or 1


def score_item_match(message_text: str, item: dict) -> int:
    text = normalize_message_text(message_text)
    name = normalize_message_text(str(item.get("name", "")))
    description = normalize_message_text(str(item.get("description", "")))
    tags = normalize_message_text(" ".join(item.get("tags", [])))

    if name and name in text:
        return 150 + len(name)

    item_tokens = tokenize(f"{name} {description} {tags}")
    message_tokens = tokenize(text)
    overlap = len(item_tokens.intersection(message_tokens))
    if overlap:
        return overlap * 10
    return 0


def classify_message_intent(message_text: str, matched_items: list[dict] | None = None) -> dict:
    normalized = normalize_message_text(message_text)
    tokens = set(normalized.split())
    matched_items = matched_items or []
    has_order_tokens = bool(tokens & ORDER_HINTS)
    has_price_tokens = bool(tokens & PRICE_HINTS)
    has_availability_tokens = bool(tokens & AVAILABILITY_HINTS)
    has_recommendation_tokens = bool(tokens & RECOMMENDATION_HINTS)
    has_contact_tokens = bool(tokens & CONTACT_HINTS)
    has_hours_tokens = bool(tokens & HOURS_HINTS)
    has_numeric_quantity = extract_numeric_quantity(message_text) is not None

    scores = {
        "place_order": 0,
        "ask_price": 0,
        "ask_availability": 0,
        "ask_recommendation": 0,
        "ask_contact": 0,
        "ask_hours": 0,
        "greeting": 0,
        "general_info": 0,
    }

    if has_order_tokens:
        scores["place_order"] += 3
    if has_price_tokens:
        scores["ask_price"] += 5
    if has_availability_tokens:
        scores["ask_availability"] += 2
    if has_recommendation_tokens:
        scores["ask_recommendation"] += 2
    if has_contact_tokens:
        scores["ask_contact"] += 2
    if has_hours_tokens:
        scores["ask_hours"] += 2
    if tokens & GREETING_HINTS:
        scores["greeting"] += 2
    if matched_items:
        if has_order_tokens or has_numeric_quantity:
            scores["place_order"] += 2
        if has_price_tokens:
            scores["ask_price"] += 2
        if has_availability_tokens:
            scores["ask_availability"] += 2
        if has_recommendation_tokens or not (has_order_tokens or has_price_tokens or has_availability_tokens):
            scores["ask_recommendation"] += 1
    if has_numeric_quantity and has_order_tokens:
        scores["place_order"] += 3
    if has_price_tokens and not has_order_tokens:
        scores["place_order"] = max(0, scores["place_order"] - 2)
    if has_contact_tokens:
        scores["ask_contact"] += 2
    if has_hours_tokens:
        scores["ask_hours"] += 2
    if "?" in message_text:
        scores["general_info"] += 1
    scores["general_info"] += 1

    intent, top_score = max(scores.items(), key=lambda row: row[1])
    total_score = sum(scores.values()) or 1
    confidence = round(min(0.98, max(0.35, top_score / total_score + 0.25)), 2)
    return {
        "intent": intent,
        "confidence": confidence,
        "scores": scores,
        "normalizedText": normalized,
    }


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


async def get_or_create_public_conversation(tenant: dict, conversation_id: str | None = None) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    if conversation_id:
        conversation_oid = parse_object_id(conversation_id, "conversationId")
        conversation = await db.conversations.find_one(
            {
                "_id": conversation_oid,
                "tenantId": tenant["_id"],
                "channel": "website",
            }
        )
        if conversation:
            return conversation

    conversation = {
        "tenantId": tenant["_id"],
        "branchId": None,
        "customerId": None,
        "customerUserId": None,
        "channel": "website",
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


async def retrieve_tenant_knowledge(tenant: dict, query_text: str, intent_profile: dict | None = None) -> list[dict]:
    await index_tenant_profile_for_rag(tenant)
    retrieval_query = query_text
    if intent_profile:
        retrieval_query = f"{query_text}\nintent:{intent_profile.get('intent', '')}"
    return await hybrid_retrieve_knowledge(tenant, retrieval_query, limit=5)


async def retrieve_sellable_items(tenant: dict) -> list[dict]:
    db = get_database()
    return await db.items.find(
        {
            "tenantId": tenant["_id"],
            "status": "active",
            "$or": [{"isSellable": True}, {"isBookable": True}],
        }
    ).to_list(length=100)


def rank_matching_items(message_text: str, items: list[dict]) -> list[dict]:
    ranked_items = sorted(
        [(item, score_item_match(message_text, item)) for item in items],
        key=lambda row: row[1],
        reverse=True,
    )
    return [row[0] for row in ranked_items if row[1] > 0][:3]


def infer_draft_transaction_type(primary_item: dict, intent_profile: dict) -> str:
    if primary_item.get("isBookable") and not primary_item.get("isSellable"):
        return "booking_request"
    if intent_profile.get("intent") == "ask_price":
        return "quote_request"
    if intent_profile.get("intent") == "ask_availability":
        return "inquiry"
    return "order"


def build_draft_order(tenant: dict, message_text: str, matched_items: list[dict], intent_profile: dict) -> dict:
    if not matched_items:
        return {}

    primary_item = matched_items[0]
    should_prepare_draft = intent_profile.get("intent") == "place_order"
    if not should_prepare_draft:
        return {}

    quantity = extract_quantity(message_text, primary_item.get("name", ""))
    now = datetime.now(timezone.utc)
    return {
        "tenantId": tenant["_id"],
        "transactionType": infer_draft_transaction_type(primary_item, intent_profile),
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
                "itemType": item.get("itemType", ""),
            }
            for item in matched_items
        ],
        "status": "awaiting_confirmation",
        "source": "assistant_planner",
        "suggestedAt": now,
    }


def build_system_prompt(
    tenant: dict,
    knowledge_docs: list[dict],
    draft_order: dict,
    intent_profile: dict,
    language_mode: str,
) -> str:
    knowledge_text = "\n\n".join(
        f"{doc.get('title', 'Knowledge')} ({doc.get('matchType', 'source')}, confidence {doc.get('confidence', 0)}): "
        f"{(doc.get('excerpt') or doc.get('content', ''))[:500]}"
        for doc in knowledge_docs
    ) or "No extra tenant knowledge found."
    draft_text = "No draft order prepared."
    if draft_order.get("items"):
        draft_text = "; ".join(
            f"{item['quantity']} x {item['name']} ({item['currency']} {item['unitPrice']})"
            for item in draft_order["items"]
        )

    category_name = tenant.get("categoryConfig", {}).get("name", "")
    category_config = tenant.get("categoryConfig", {}) or {}
    ai_hints = category_config.get("aiHints", {}) or {}
    ai_prompt_fragments = category_config.get("aiPromptFragments", []) or []
    fulfillment_hints = category_config.get("fulfillmentRules") or (((tenant.get("settings") or {}).get("categoryHints") or {}).get("fulfillment") or {})
    analytics_hints = category_config.get("analyticsConfig") or (((tenant.get("settings") or {}).get("categoryHints") or {}).get("analytics") or {})
    tenant_language_mode = get_language_mode(tenant.get("settings"))
    effective_language_mode = language_mode if tenant_language_mode == "mixed" else tenant_language_mode

    response_style = build_ai_localization_guidance(effective_language_mode, tenant)

    return (
        f"You are BizXus AI for the business '{tenant.get('name', 'Business')}'. "
        "Answer only using the business knowledge provided. "
        "If the customer wants to place an order, suggest items and clearly ask them to confirm the draft order. "
        "Never say an order is already placed until the app confirms it. "
        "Keep answers concise, practical, and business-safe.\n\n"
        f"{response_style}\n"
        f"Detected intent: {intent_profile.get('intent', 'general_info')}\n"
        f"Detected language mode: {language_mode}\n"
        f"Tenant language preference: {tenant_language_mode}\n"
        f"Business category: {category_name}\n"
        f"Business description: {tenant.get('description', '')}\n"
        f"Business contact: {tenant.get('contact', {})}\n"
        f"Category AI hints: {ai_hints}\n"
        f"Category prompt fragments: {ai_prompt_fragments}\n"
        f"Category fulfillment rules: {fulfillment_hints}\n"
        f"Category analytics focus: {analytics_hints}\n"
        "Local quality checklist: keep wording usable for Pakistani customers, prefer WhatsApp/contact style language where relevant, use PKR for prices, and end with a clear next step when useful.\n"
        f"Retrieved tenant knowledge:\n{knowledge_text}\n\n"
        f"Current draft order: {draft_text}"
    )


def build_llm_messages(system_prompt: str, user_message: str, recent_messages: list[dict]) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    for message in recent_messages[-6:]:
        if message.get("sender") == "customer":
            messages.append({"role": "user", "content": message.get("messageText", "")})
        elif message.get("sender") == "ai":
            messages.append({"role": "assistant", "content": message.get("messageText", "")})
    messages.append({"role": "user", "content": user_message})
    return messages


async def generate_openai_response(system_prompt: str, user_message: str, recent_messages: list[dict]) -> str | None:
    if not settings.openai_api_key:
        return None

    messages = build_llm_messages(system_prompt, user_message, recent_messages)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": messages,
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


async def generate_groq_response(system_prompt: str, user_message: str, recent_messages: list[dict]) -> str | None:
    if not settings.groq_api_key:
        return None

    messages = build_llm_messages(system_prompt, user_message, recent_messages)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.groq_model,
                    "messages": messages,
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def format_contact_summary(tenant: dict, language_mode: str) -> str:
    contact = tenant.get("contact", {}) or {}
    phone = contact.get("phone") or "not listed"
    email = contact.get("email") or "not listed"
    if language_mode in {"roman_urdu", "mixed"}:
        return f"Contact details yeh hain: phone {phone}, email {email}."
    return f"Here are the business contact details: phone {phone}, email {email}."


def format_address_summary(tenant: dict, language_mode: str) -> str:
    address = tenant.get("address", {}) or {}
    city = address.get("city") or "not listed"
    province = address.get("province") or "not listed"
    address_line = address.get("addressLine1") or address.get("street") or "not listed"
    if language_mode in {"roman_urdu", "mixed"}:
        return f"Business address: {address_line}, {city}, {province}."
    return f"Business address: {address_line}, {city}, {province}."


def generate_rule_based_response(
    tenant: dict,
    knowledge_docs: list[dict],
    draft_order: dict,
    intent_profile: dict,
    matched_items: list[dict],
    language_mode: str,
) -> str:
    intent = intent_profile.get("intent", "general_info")

    if draft_order.get("items"):
        primary = draft_order["items"][0]
        suggested_names = ", ".join(item["name"] for item in draft_order.get("suggestedItems", []))
        if language_mode in {"roman_urdu", "mixed"}:
            return (
                f"Maine {primary['name']} find kar liya hai aur quantity {primary['quantity']} ka draft tayar kar diya hai. "
                f"Aap neeche draft confirm kar sakte hain. Matching options: {suggested_names}."
            )
        return (
            f"I found {primary['name']} and prepared a draft for quantity {primary['quantity']}. "
            f"You can confirm the draft below. Matching options: {suggested_names}."
        )

    if intent == "ask_price" and matched_items:
        primary = matched_items[0]
        if language_mode in {"roman_urdu", "mixed"}:
            return f"{primary.get('name', 'This item')} ki price {primary.get('currency', 'PKR')} {float(primary.get('price', 0))} hai."
        return f"The price for {primary.get('name', 'this item')} is {primary.get('currency', 'PKR')} {float(primary.get('price', 0))}."

    if intent == "ask_availability" and matched_items:
        primary = matched_items[0]
        if language_mode in {"roman_urdu", "mixed"}:
            return f"Ji, {primary.get('name', 'ye item')} available lag raha hai. Agar chahiye ho to quantity bata dein, main draft bana doon."
        return f"Yes, {primary.get('name', 'this item')} appears to be available. If you want it, tell me the quantity and I can prepare a draft."

    if intent == "ask_contact":
        return f"{format_contact_summary(tenant, language_mode)} {format_address_summary(tenant, language_mode)}"

    if intent == "ask_hours":
        if knowledge_docs:
            lead = (knowledge_docs[0].get("excerpt") or knowledge_docs[0].get("content", ""))[:220]
            if language_mode in {"roman_urdu", "mixed"}:
                return f"Available business info ke mutabiq: {lead}"
            return f"From the available business information: {lead}"
        if language_mode in {"roman_urdu", "mixed"}:
            return "Business hours abhi knowledge base mein clearly nahi milay. Aap contact details ke liye pooch sakte hain."
        return "Business hours are not clearly available in the current knowledge yet. You can ask for contact details instead."

    if intent == "ask_recommendation" and matched_items:
        suggestions = ", ".join(item.get("name", "Item") for item in matched_items[:3])
        if language_mode in {"roman_urdu", "mixed"}:
            return f"Popular ya matching options mein yeh aa rahe hain: {suggestions}. Agar kisi ek ka draft chahiye ho to quantity bata dein."
        return f"Here are some matching options: {suggestions}. If you want a draft for one of them, tell me the quantity."

    if knowledge_docs:
        lead = knowledge_docs[0]
        prefix = "Yeh business info mili hai:" if language_mode in {"roman_urdu", "mixed"} else "Here is what I found from the business:"
        suffix = (
            "Agar order banana ho to item name aur quantity bhej dein."
            if language_mode in {"roman_urdu", "mixed"}
            else "If you want an order draft, mention the item name and quantity."
        )
        return f"{prefix} {(lead.get('excerpt') or lead.get('content', ''))[:280]} {suffix}"

    if language_mode in {"roman_urdu", "mixed"}:
        return (
            f"Main {tenant.get('name', 'is business')} ke products, services, prices, aur draft orders mein help kar sakta hoon. "
            "Misal: '2 burgers order kar do' ya 'burger ki price kya hai?'."
        )
    return (
        f"I can help with {tenant.get('name', 'this business')} products, services, prices, and draft orders. "
        "For example: 'order 2 burgers' or 'what is the burger price?'."
    )


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
        "conversation": serialize_document(conversation),
        "messages": messages,
        "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
    }


async def send_public_chat_message(slug: str, message_text: str, conversation_id: str | None = None) -> dict:
    db = get_database()
    tenant = await get_public_chat_tenant_or_404(slug)
    if "ai_chat" not in tenant.get("enabledModuleCodes", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI chat is disabled for this business.")
    await ensure_tenant_module_usage_available(tenant["_id"], "ai_chat")
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
        "conversation": serialize_document(conversation),
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
