from datetime import datetime, timedelta, timezone

from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.category_config_service import build_category_analytics_insights
from app.services.localization_service import get_language_mode, localize_business_summary
from app.services.transaction_workflow_service import ORDER_TRANSACTION_TYPES


async def get_analytics_summary(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "analytics")

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    trend_start = (today_start - timedelta(days=6))

    total_customers = await db.customers.count_documents({"tenantId": tenant_oid})
    total_items = await db.items.count_documents({"tenantId": tenant_oid, "status": {"$ne": "archived"}})
    total_transactions = await db.transactions.count_documents({"tenantId": tenant_oid})
    total_orders = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "order"})
    total_quotes = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "quote_request"})
    total_bookings = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "booking_request"})
    total_inquiries = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "inquiry"})
    today_orders = await db.transactions.count_documents(
        {
            "tenantId": tenant_oid,
            "transactionType": "order",
            "createdAt": {"$gte": today_start},
        }
    )
    marketplace_order_count = await db.transactions.count_documents(
        {
            "tenantId": tenant_oid,
            "transactionType": "order",
            "source": "customer_portal",
        }
    )

    revenue_pipeline = [
        {
            "$match": {
                "tenantId": tenant_oid,
                "transactionType": {"$in": list(ORDER_TRANSACTION_TYPES)},
                "status": {"$ne": "cancelled"},
            }
        },
        {
            "$group": {
                "_id": None,
                "grossRevenue": {"$sum": "$pricing.total"},
                "averageOrderValue": {"$avg": "$pricing.total"},
            }
        },
    ]
    revenue_rows = await db.transactions.aggregate(revenue_pipeline).to_list(length=1)
    revenue = revenue_rows[0] if revenue_rows else {"grossRevenue": 0, "averageOrderValue": 0}

    low_stock_cursor = (
        db.items.find(
            {
                "tenantId": tenant_oid,
                "status": "active",
                "isStockTracked": True,
                "$expr": {"$lte": ["$stock.quantity", "$stock.lowStockThreshold"]},
            }
        )
        .sort("stock.quantity", 1)
        .limit(5)
    )
    low_stock_items = [serialize_document(item) async for item in low_stock_cursor]

    recent_transactions_cursor = (
        db.transactions.find({"tenantId": tenant_oid})
        .sort("createdAt", -1)
        .limit(5)
    )
    recent_transactions = [serialize_document(order) async for order in recent_transactions_cursor]
    trend_rows = await db.transactions.aggregate(
        [
            {"$match": {"tenantId": tenant_oid, "createdAt": {"$gte": trend_start}}},
            {
                "$group": {
                    "_id": {
                        "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}},
                        "transactionType": "$transactionType",
                    },
                    "count": {"$sum": 1},
                    "revenue": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$eq": ["$transactionType", "order"]},
                                        {"$ne": ["$status", "cancelled"]},
                                    ]
                                },
                                "$pricing.total",
                                0,
                            ]
                        }
                    },
                }
            },
        ]
    ).to_list(length=None)
    trend_map = {(row["_id"]["date"], row["_id"]["transactionType"]): row for row in trend_rows}
    trends = []
    for offset in range(7):
        day = trend_start + timedelta(days=offset)
        date_key = day.strftime("%Y-%m-%d")
        order_row = trend_map.get((date_key, "order"), {})
        quote_row = trend_map.get((date_key, "quote_request"), {})
        booking_row = trend_map.get((date_key, "booking_request"), {})
        inquiry_row = trend_map.get((date_key, "inquiry"), {})
        trends.append(
            {
                "date": date_key,
                "label": day.strftime("%d %b"),
                "orders": int(order_row.get("count", 0) or 0),
                "quotes": int(quote_row.get("count", 0) or 0),
                "bookings": int(booking_row.get("count", 0) or 0),
                "inquiries": int(inquiry_row.get("count", 0) or 0),
                "revenue": round(float(order_row.get("revenue", 0) or 0), 2),
            }
        )

    top_item_rows = await db.transactions.aggregate(
        [
            {
                "$match": {
                    "tenantId": tenant_oid,
                    "transactionType": {"$in": list(ORDER_TRANSACTION_TYPES)},
                    "status": {"$ne": "cancelled"},
                    "items": {"$exists": True, "$ne": []},
                }
            },
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": "$items.itemId",
                    "name": {"$first": "$items.name"},
                    "quantity": {"$sum": "$items.quantity"},
                    "revenue": {"$sum": "$items.subtotal"},
                    "orders": {"$sum": 1},
                    "lastOrderedAt": {"$max": "$createdAt"},
                }
            },
            {"$sort": {"revenue": -1, "quantity": -1}},
            {"$limit": 8},
        ]
    ).to_list(length=8)
    item_type_map = {}
    if top_item_rows:
        item_ids = [row["_id"] for row in top_item_rows if row.get("_id")]
        item_type_map = {
            item["_id"]: item
            async for item in db.items.find({"_id": {"$in": item_ids}}, {"itemType": 1, "name": 1})
        }
    top_items = [
        {
            "itemId": str(row.get("_id")) if row.get("_id") else None,
            "name": row.get("name") or item_type_map.get(row.get("_id"), {}).get("name") or "Unknown item",
            "itemType": item_type_map.get(row.get("_id"), {}).get("itemType", "product"),
            "quantity": int(row.get("quantity", 0) or 0),
            "orders": int(row.get("orders", 0) or 0),
            "revenue": round(float(row.get("revenue", 0) or 0), 2),
            "lastOrderedAt": row.get("lastOrderedAt").isoformat() if row.get("lastOrderedAt") else None,
        }
        for row in top_item_rows
    ]

    approved_quotes = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "quote_request", "status": "approved"})
    confirmed_bookings = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "booking_request", "status": "confirmed"})
    responded_inquiries = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "inquiry", "status": {"$in": ["responded", "closed"]}})
    conversion = {
        "marketplaceShare": _safe_percentage(marketplace_order_count, total_orders),
        "quoteApprovalRate": _safe_percentage(approved_quotes, total_quotes),
        "bookingConfirmationRate": _safe_percentage(confirmed_bookings, total_bookings),
        "inquiryResponseRate": _safe_percentage(responded_inquiries, total_inquiries),
        "orderMixShare": _safe_percentage(total_orders, total_transactions),
    }
    dashboard_summary = _build_dashboard_summary(
        tenant_name=tenant.get("name", "This business"),
        language_mode=get_language_mode(tenant.get("settings")),
        summary={
            "totalTransactions": total_transactions,
            "totalOrders": total_orders,
            "totalQuotes": total_quotes,
            "totalBookings": total_bookings,
            "totalInquiries": total_inquiries,
        },
        revenue={
            "grossRevenue": round(float(revenue.get("grossRevenue", 0) or 0), 2),
            "averageOrderValue": round(float(revenue.get("averageOrderValue", 0) or 0), 2),
        },
        conversion=conversion,
        top_items=top_items,
        low_stock_items=low_stock_items,
        trends=trends,
    )
    category_insights = build_category_analytics_insights(tenant, {
        "totalTransactions": total_transactions,
        "totalOrders": total_orders,
        "totalQuotes": total_quotes,
        "totalBookings": total_bookings,
        "totalInquiries": total_inquiries,
        "marketplaceOrderCount": marketplace_order_count,
        "grossRevenue": round(float(revenue.get("grossRevenue", 0) or 0), 2),
    }, conversion, low_stock_items)

    return {
        "summary": {
            "totalCustomers": total_customers,
            "totalItems": total_items,
            "totalTransactions": total_transactions,
            "totalOrders": total_orders,
            "totalQuotes": total_quotes,
            "totalBookings": total_bookings,
            "totalInquiries": total_inquiries,
            "todayOrders": today_orders,
            "marketplaceOrderCount": marketplace_order_count,
        },
        "revenue": {
            "grossRevenue": round(float(revenue.get("grossRevenue", 0) or 0), 2),
            "averageOrderValue": round(float(revenue.get("averageOrderValue", 0) or 0), 2),
        },
        "trends": trends,
        "topItems": top_items,
        "conversion": conversion,
        "dashboardSummary": dashboard_summary,
        "categoryGuidance": {
            "categoryName": ((tenant.get("settings") or {}).get("categoryHints") or {}).get("categoryName", ""),
            "focusMetrics": (((tenant.get("settings") or {}).get("categoryHints") or {}).get("analytics") or {}).get("focusMetrics", []),
            "suggestions": (((tenant.get("settings") or {}).get("categoryHints") or {}).get("analytics") or {}).get("suggestions", []),
            "insights": category_insights,
        },
        "lowStockItems": low_stock_items,
        "recentTransactions": recent_transactions,
        "generatedAt": now.isoformat(),
    }


def _safe_percentage(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _build_dashboard_summary(tenant_name: str, language_mode: str, summary: dict, revenue: dict, conversion: dict, top_items: list[dict], low_stock_items: list[dict], trends: list[dict]) -> str:
    total_transactions = summary.get("totalTransactions", 0)
    total_orders = summary.get("totalOrders", 0)
    gross_revenue = revenue.get("grossRevenue", 0)
    avg_order_value = revenue.get("averageOrderValue", 0)
    top_item = top_items[0]["name"] if top_items else "no clear top item yet"
    if language_mode == "roman_urdu":
        low_stock_note = f"{len(low_stock_items)} low-stock item(s) ko tawajjo chahiye." if low_stock_items else "Filhal low-stock pressure nahi hai."
    elif language_mode == "mixed":
        low_stock_note = f"{len(low_stock_items)} low-stock item(s) ko attention chahiye." if low_stock_items else "Filhal low-stock pressure nahi hai."
    else:
        low_stock_note = f"{len(low_stock_items)} low-stock item(s) need attention." if low_stock_items else "No low-stock pressure right now."
    last_two = trends[-2:] if len(trends) >= 2 else trends
    revenue_delta = 0
    if len(last_two) == 2:
        revenue_delta = round(last_two[-1]["revenue"] - last_two[0]["revenue"], 2)
    if language_mode == "roman_urdu":
        momentum_note = (
            f"Recent days ke muqable mein revenue PKR {revenue_delta} up hai."
            if revenue_delta > 0
            else f"Recent days ke muqable mein revenue PKR {abs(revenue_delta)} down hai."
            if revenue_delta < 0
            else "Recent days mein revenue stable raha hai."
        )
    elif language_mode == "mixed":
        momentum_note = (
            f"Recent days ke muqable mein revenue PKR {revenue_delta} up hai."
            if revenue_delta > 0
            else f"Recent days ke muqable mein revenue PKR {abs(revenue_delta)} down hai."
            if revenue_delta < 0
            else "Recent days mein revenue stable hai."
        )
    else:
        momentum_note = (
            f"Revenue gained PKR {revenue_delta} versus the earlier recent day."
            if revenue_delta > 0
            else f"Revenue is down PKR {abs(revenue_delta)} versus the earlier recent day."
            if revenue_delta < 0
            else "Revenue is stable across the latest visible days."
        )
    return localize_business_summary(
        tenant_name=tenant_name,
        language_mode=language_mode,
        total_transactions=total_transactions,
        total_orders=total_orders,
        gross_revenue=gross_revenue,
        avg_order_value=avg_order_value,
        top_item=top_item,
        marketplace_share=conversion.get("marketplaceShare", 0),
        quote_approval_rate=conversion.get("quoteApprovalRate", 0),
        momentum_note=momentum_note,
        low_stock_note=low_stock_note,
    )
