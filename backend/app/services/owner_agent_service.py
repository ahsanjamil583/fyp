from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.schemas.owner_agent_schema import OwnerAgentChatRequest
from app.services.ai_chat_service import detect_language_mode, load_conversation_messages, save_message
from app.services.analytics_service import get_analytics_summary
from app.services.business_notification_service import sync_low_stock_notifications
from app.services.reporting_service import get_daily_summary

OWNER_AGENT_TOOLS = [
    {"code": "catalog_count", "name": "Catalog Count", "description": "Counts and lists active catalog products/services."},
    {"code": "business_summary", "name": "Business Summary", "description": "Summarizes orders, revenue, customers, and recent performance."},
    {"code": "low_stock", "name": "Low Stock", "description": "Finds stock-tracked items that need reorder attention."},
    {"code": "top_items", "name": "Top Items", "description": "Shows best-selling items by quantity and revenue."},
    {"code": "pending_orders", "name": "Pending Orders", "description": "Lists pending or recently created order/booking/quote transactions."},
    {"code": "customer_chats", "name": "Customer Chats", "description": "Summarizes website, customer portal, and WhatsApp conversations."},
    {"code": "payment_health", "name": "Payment Health", "description": "Reviews unpaid, partial, and paid transaction totals."},
    {"code": "promotion_ideas", "name": "Promotion Ideas", "description": "Suggests simple offers using top items, slow items, and low-stock pressure."},
]


async def _get_owner_agent_access(tenant_id: str, user: dict) -> tuple[ObjectId, dict]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "owner_agent")
    await ensure_tenant_module_enabled(tenant_oid, "analytics")
    await ensure_tenant_module_enabled(tenant_oid, "reports")
    await ensure_tenant_module_enabled(tenant_oid, "notifications")
    return tenant_oid, tenant


async def _get_or_create_owner_conversation(tenant: dict, user: dict) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    conversation = await db.conversations.find_one(
        {"tenantId": tenant["_id"], "channel": "owner_agent", "ownerUserId": user["_id"], "status": "open"}
    )
    if conversation:
        return conversation
    conversation = {
        "tenantId": tenant["_id"],
        "branchId": None,
        "customerId": None,
        "customerUserId": None,
        "ownerUserId": user["_id"],
        "channel": "owner_agent",
        "status": "open",
        "languageDetected": "english",
        "pendingOrderDraft": {},
        "summary": "Owner-side business assistant conversation.",
        "lastIntent": "",
        "lastIntentConfidence": 0.0,
        "lastAssistantSource": "owner_agent",
        "lastKnowledgeCount": 0,
        "lastMessageAt": now,
        "createdAt": now,
        "updatedAt": now,
    }
    conversation["_id"] = (await db.conversations.insert_one(conversation)).inserted_id
    return conversation


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").lower().strip().split())


def _classify_owner_intent(text: str) -> str:
    normalized = _normalize_text(text)
    if any(phrase in normalized for phrase in ["kitny products", "kitne products", "how many products", "product count", "total products", "list products", "items hain", "products hyn", "products hain"]):
        return "catalog_count"
    if any(word in normalized for word in ["low stock", "inventory", "reorder", "khatam", "kam"]):
        return "low_stock"
    if "stock" in normalized and not any(phrase in normalized for phrase in ["kitny products", "kitne products", "how many products", "total products"]):
        return "low_stock"
    if any(word in normalized for word in ["top", "best", "popular", "selling", "bik", "zayada", "zyada"]):
        return "top_items"
    if any(word in normalized for word in ["pending", "new order", "orders", "booking", "quote", "inquiry"]):
        return "pending_orders"
    if any(word in normalized for word in ["chat", "conversation", "whatsapp", "customer query", "message"]):
        return "customer_chats"
    if any(word in normalized for word in ["payment", "paid", "unpaid", "refund", "cod", "jazzcash", "easypaisa"]):
        return "payment_health"
    if any(word in normalized for word in ["promotion", "offer", "discount", "marketing", "campaign", "sale"]):
        return "promotion_ideas"
    if any(word in normalized for word in ["report", "summary", "today", "sales", "revenue", "business", "performance", "insight"]):
        return "business_summary"
    return "business_summary"


def _money(value) -> str:
    try:
        return f"PKR {float(value or 0):,.0f}"
    except Exception:
        return "PKR 0"


async def get_owner_agent_insights(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_owner_agent_access(tenant_id, user)
    await sync_low_stock_notifications(tenant_oid)
    analytics = await get_analytics_summary(tenant_id, user)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    pending_count = await db.transactions.count_documents(
        {"tenantId": tenant_oid, "status": {"$in": ["new", "pending", "draft", "requested", "confirmed"]}}
    )
    unread_alerts = await db.business_notifications.count_documents({"tenantId": tenant_oid, "status": "unread"})
    today_conversations = await db.conversations.count_documents({"tenantId": tenant_oid, "lastMessageAt": {"$gte": today_start}})
    unpaid_total_rows = await db.transactions.aggregate(
        [
            {"$match": {"tenantId": tenant_oid, "paymentStatus": {"$in": ["unpaid", "partially_paid"]}, "status": {"$ne": "cancelled"}}},
            {"$group": {"_id": None, "amount": {"$sum": "$pricing.total"}, "count": {"$sum": 1}}},
        ]
    ).to_list(length=1)
    unpaid = unpaid_total_rows[0] if unpaid_total_rows else {"amount": 0, "count": 0}
    cards = [
        {"label": "Today Orders", "value": analytics.get("summary", {}).get("todayOrders", 0), "hint": "Orders created today"},
        {"label": "Gross Revenue", "value": _money(analytics.get("revenue", {}).get("grossRevenue", 0)), "hint": "All non-cancelled order revenue"},
        {"label": "Low Stock", "value": len(analytics.get("lowStockItems", [])), "hint": "Items at/below threshold"},
        {"label": "Pending Work", "value": pending_count, "hint": "Transactions needing review"},
        {"label": "Unread Alerts", "value": unread_alerts, "hint": "Business notifications"},
        {"label": "Chats Today", "value": today_conversations, "hint": "Customer/WhatsApp/website conversations"},
        {"label": "Unpaid Amount", "value": _money(unpaid.get("amount", 0)), "hint": f"{unpaid.get('count', 0)} unpaid/partial transactions"},
    ]
    actions = []
    if analytics.get("lowStockItems"):
        actions.append("Review and reorder low-stock items before accepting more orders.")
    if pending_count:
        actions.append("Open transactions and process pending customer requests.")
    if unpaid.get("count", 0):
        actions.append("Follow up unpaid/partial payments or mark COD collections after delivery.")
    if analytics.get("topItems"):
        actions.append(f"Promote {analytics['topItems'][0].get('name', 'your top item')} because it is currently performing best.")
    return {
        "tenant": serialize_document(tenant),
        "cards": cards,
        "actions": actions,
        "analyticsSummary": analytics.get("dashboardSummary", ""),
        "topItems": analytics.get("topItems", [])[:5],
        "lowStockItems": analytics.get("lowStockItems", [])[:5],
        "recentTransactions": analytics.get("recentTransactions", [])[:5],
        "tools": OWNER_AGENT_TOOLS,
        "generatedAt": now.isoformat(),
    }


async def chat_with_owner_agent(tenant_id: str, payload: OwnerAgentChatRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_owner_agent_access(tenant_id, user)
    conversation = await _get_or_create_owner_conversation(tenant, user)
    language = detect_language_mode(payload.messageText)
    await save_message(conversation, tenant_oid, "owner", payload.messageText, intent="owner_query", confidence=1.0)
    intent = _classify_owner_intent(payload.messageText)
    context = await _build_owner_context(tenant_id, tenant_oid, user, intent)
    reply = _build_owner_reply(tenant, payload.messageText, intent, context, language)
    tool_calls = [{"tool": intent, "status": "completed", "summary": f"Owner agent used {intent.replace('_', ' ')} context."}]
    assistant_message = await save_message(conversation, tenant_oid, "assistant", reply, intent=intent, confidence=0.9, tool_calls=tool_calls)
    await db.conversations.update_one(
        {"_id": conversation["_id"]},
        {
            "$set": {
                "languageDetected": language,
                "lastIntent": intent,
                "lastIntentConfidence": 0.9,
                "lastAssistantSource": "owner_agent",
                "lastMessageAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    history = await load_conversation_messages(conversation["_id"]) if payload.includeHistory else []
    return {
        "tenant": serialize_document(tenant),
        "conversationId": str(conversation["_id"]),
        "reply": reply,
        "intent": intent,
        "toolCalls": tool_calls,
        "context": context,
        "message": serialize_document(assistant_message),
        "history": history,
    }


async def _build_owner_context(tenant_id: str, tenant_oid: ObjectId, user: dict, intent: str) -> dict:
    db = get_database()
    analytics = await get_analytics_summary(tenant_id, user)
    context = {
        "analytics": analytics,
        "lowStockItems": analytics.get("lowStockItems", [])[:8],
        "topItems": analytics.get("topItems", [])[:8],
        "recentTransactions": analytics.get("recentTransactions", [])[:8],
    }
    if intent == "catalog_count":
        cursor = db.items.find({"tenantId": tenant_oid, "status": {"$ne": "archived"}}).sort("createdAt", -1).limit(200)
        context["catalogItems"] = [serialize_document(row) async for row in cursor]
        context["activeProductCount"] = await db.items.count_documents({"tenantId": tenant_oid, "status": "active", "itemType": "product"})
        context["activeItemCount"] = await db.items.count_documents({"tenantId": tenant_oid, "status": "active"})
    if intent == "business_summary":
        try:
            context["dailySummary"] = await get_daily_summary(tenant_id, user)
        except Exception:
            context["dailySummary"] = {}
    if intent == "pending_orders":
        cursor = db.transactions.find(
            {"tenantId": tenant_oid, "status": {"$in": ["new", "pending", "draft", "requested", "confirmed"]}}
        ).sort("createdAt", -1).limit(8)
        context["pendingTransactions"] = [serialize_document(row) async for row in cursor]
    if intent == "customer_chats":
        since = datetime.now(timezone.utc) - timedelta(days=7)
        pipeline = [
            {"$match": {"tenantId": tenant_oid, "lastMessageAt": {"$gte": since}}},
            {"$group": {"_id": "$channel", "count": {"$sum": 1}, "lastMessageAt": {"$max": "$lastMessageAt"}}},
            {"$sort": {"count": -1}},
        ]
        rows = await db.conversations.aggregate(pipeline).to_list(length=20)
        context["conversationBreakdown"] = [
            {"channel": row.get("_id") or "unknown", "count": row.get("count", 0), "lastMessageAt": row.get("lastMessageAt").isoformat() if row.get("lastMessageAt") else None}
            for row in rows
        ]
        recent_cursor = db.conversations.find({"tenantId": tenant_oid}).sort("lastMessageAt", -1).limit(5)
        context["recentConversations"] = [serialize_document(row) async for row in recent_cursor]
    if intent == "payment_health":
        rows = await db.transactions.aggregate(
            [
                {"$match": {"tenantId": tenant_oid, "status": {"$ne": "cancelled"}}},
                {"$group": {"_id": "$paymentStatus", "count": {"$sum": 1}, "amount": {"$sum": "$pricing.total"}}},
            ]
        ).to_list(length=20)
        context["paymentBreakdown"] = [
            {"paymentStatus": row.get("_id") or "unknown", "count": row.get("count", 0), "amount": round(float(row.get("amount", 0) or 0), 2)}
            for row in rows
        ]
    if intent == "promotion_ideas":
        top_ids = {row.get("itemId") for row in analytics.get("topItems", []) if row.get("itemId")}
        cursor = db.items.find({"tenantId": tenant_oid, "status": "active"}).sort("createdAt", 1).limit(20)
        slow_candidates = []
        async for item in cursor:
            if str(item.get("_id")) not in top_ids:
                slow_candidates.append(serialize_document(item))
            if len(slow_candidates) >= 5:
                break
        context["slowMovingCandidates"] = slow_candidates
    return context


def _build_owner_reply(tenant: dict, message_text: str, intent: str, context: dict, language: str) -> str:
    analytics = context.get("analytics") or {}
    summary = analytics.get("summary") or {}
    revenue = analytics.get("revenue") or {}
    top_items = context.get("topItems") or []
    low_stock_items = context.get("lowStockItems") or []
    roman = language == "roman_urdu" or language == "mixed"

    if intent == "catalog_count":
        catalog_items = context.get("catalogItems") or []
        active_count = context.get("activeItemCount", len(catalog_items))
        active_product_count = context.get("activeProductCount", 0)
        if not catalog_items:
            return "Is business mein abhi koi catalog item/product add nahi hua." if roman else "This business does not have any catalog items/products yet."
        lines = [
            f"{tenant.get('name', 'Business')} mein total active catalog items: {active_count}. Active products: {active_product_count}." if not roman else f"{tenant.get('name', 'Business')} mein total active catalog items {active_count} hain. Active products {active_product_count} hain."
        ]
        for item in catalog_items[:12]:
            if item.get("status") == "active":
                stock = item.get("stock") or {}
                lines.append(f"- {item.get('name', 'Item')} ({item.get('itemType', 'item')}) — stock {stock.get('quantity', 0)}")
        return "\n".join(lines)

    if intent == "low_stock":
        if not low_stock_items:
            return "Filhal low-stock pressure nahi hai. Sab tracked items threshold se upar lag rahe hain." if roman else "No low-stock pressure right now. Your tracked items are currently above their thresholds."
        lines = ["Low-stock items:" if not roman else "Low-stock items jin par tawajjo chahiye:"]
        for item in low_stock_items[:5]:
            stock = item.get("stock") or {}
            lines.append(f"- {item.get('name', 'Item')}: {stock.get('quantity', 0)} left / threshold {stock.get('lowStockThreshold', 0)}")
        lines.append("Recommendation: reorder these before accepting more orders." if not roman else "Suggestion: in items ko reorder kar lein taa ke orders miss na hon.")
        return "\n".join(lines)

    if intent == "top_items":
        if not top_items:
            return "No top-selling item is clear yet because there is not enough completed order data." if not roman else "Abhi top-selling item clear nahi hai kyun ke order data kam hai."
        lines = ["Top performing items:" if not roman else "Sab se zyada perform karne wali items:"]
        for item in top_items[:5]:
            lines.append(f"- {item.get('name', 'Item')}: {item.get('quantity', 0)} qty, {_money(item.get('revenue', 0))} revenue")
        lines.append(f"Action: promote {top_items[0].get('name', 'your top item')} on website and WhatsApp." if not roman else f"Action: {top_items[0].get('name', 'top item')} ko website aur WhatsApp par promote karein.")
        return "\n".join(lines)

    if intent == "pending_orders":
        pending = context.get("pendingTransactions") or []
        if not pending:
            return "No pending transactions need attention right now." if not roman else "Filhal koi pending transaction attention nahi maang rahi."
        lines = ["Pending work:" if not roman else "Pending kaam:"]
        for order in pending[:5]:
            customer = order.get("customerSnapshot") or {}
            lines.append(f"- {order.get('transactionNumber', 'TXN')}: {order.get('transactionType', 'order')} / {order.get('status', '')} / {customer.get('name', 'Customer')} / {_money((order.get('pricing') or {}).get('total', 0))}")
        lines.append("Action: open Transactions and update status after processing." if not roman else "Action: Transactions me ja kar status update kar dein.")
        return "\n".join(lines)

    if intent == "customer_chats":
        breakdown = context.get("conversationBreakdown") or []
        if not breakdown:
            return "No recent customer chats were found in the last 7 days." if not roman else "Last 7 din me recent customer chats nahi mile."
        lines = ["Customer chat activity in the last 7 days:" if not roman else "Last 7 din ki customer chat activity:"]
        for row in breakdown:
            lines.append(f"- {row.get('channel', 'unknown')}: {row.get('count', 0)} conversations")
        lines.append("Check AI Conversations and WhatsApp Agent pages for full chat review." if not roman else "Full review ke liye AI Conversations aur WhatsApp Agent pages check karein.")
        return "\n".join(lines)

    if intent == "payment_health":
        rows = context.get("paymentBreakdown") or []
        if not rows:
            return "No payment records are available yet." if not roman else "Abhi payment records available nahi hain."
        lines = ["Payment health:" if not roman else "Payment status:"]
        for row in rows:
            lines.append(f"- {row.get('paymentStatus', 'unknown')}: {row.get('count', 0)} transactions / {_money(row.get('amount', 0))}")
        lines.append("Action: follow up unpaid/partial orders and record collected COD/manual payments." if not roman else "Action: unpaid/partial orders follow up karein aur collected COD/manual payments record karein.")
        return "\n".join(lines)

    if intent == "promotion_ideas":
        slow = context.get("slowMovingCandidates") or []
        lines = ["Promotion ideas:" if not roman else "Promotion ideas:"]
        if top_items:
            lines.append(f"- Push bestseller: promote {top_items[0].get('name', 'top item')} as today's recommended item.")
        if slow:
            lines.append(f"- Move slow stock: create a small bundle/discount around {slow[0].get('name', 'one slow item')}.")
        if low_stock_items:
            lines.append("- Avoid heavy discounting on low-stock items until you restock.")
        lines.append("- Send the offer through your public website banner and WhatsApp customers." if not roman else "- Offer ko website banner aur WhatsApp customers par share karein.")
        return "\n".join(lines)

    # default business summary
    lines = [
        f"{tenant.get('name', 'Business')} summary:" if not roman else f"{tenant.get('name', 'Business')} ki summary:",
        f"- Total transactions: {summary.get('totalTransactions', 0)}",
        f"- Total orders: {summary.get('totalOrders', 0)}",
        f"- Today's orders: {summary.get('todayOrders', 0)}",
        f"- Gross revenue: {_money(revenue.get('grossRevenue', 0))}",
        f"- Average order value: {_money(revenue.get('averageOrderValue', 0))}",
    ]
    if top_items:
        lines.append(f"- Top item: {top_items[0].get('name', 'Item')}")
    if low_stock_items:
        lines.append(f"- Low-stock items needing attention: {len(low_stock_items)}")
    lines.append("Ask me about low stock, top items, pending orders, payments, customer chats, or promotion ideas." if not roman else "Aap low stock, top items, pending orders, payments, customer chats, ya promotion ideas ke bare me pooch sakte hain.")
    return "\n".join(lines)


async def get_owner_agent_history(tenant_id: str, user: dict, limit: int = 30) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_owner_agent_access(tenant_id, user)
    conversation = await db.conversations.find_one(
        {"tenantId": tenant_oid, "channel": "owner_agent", "ownerUserId": user["_id"], "status": "open"}
    )
    if not conversation:
        return {"tenant": serialize_document(tenant), "conversationId": "", "items": []}
    limit = min(max(limit, 1), 100)
    cursor = db.messages.find({"conversationId": conversation["_id"]}).sort("createdAt", -1).limit(limit)
    messages = [serialize_document(row) async for row in cursor]
    messages.reverse()
    return {"tenant": serialize_document(tenant), "conversationId": str(conversation["_id"]), "items": messages}
