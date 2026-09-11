from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status

from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.analytics_service import get_analytics_summary
from app.services.business_notification_service import create_business_notification, sync_low_stock_notifications


def _parse_summary_date(value: str | None, timezone_name: str = "Asia/Karachi") -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid business timezone.")
    if not value:
        return datetime.now(zone)
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=zone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Use YYYY-MM-DD for summary date.") from exc


async def _get_reporting_access(tenant_id: str, user: dict) -> tuple[str, dict]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "reports")
    return tenant_id, tenant


async def _report_timezone(db, tenant: dict) -> str:
    delivery = await db.report_delivery_settings.find_one({"tenantId": tenant["_id"]})
    return (delivery or {}).get("timezone") or (tenant.get("settings") or {}).get("timezone") or "Asia/Karachi"


def _build_hook_preview(summary: dict, tenant: dict) -> dict:
    return {
        "webhookEvent": {
            "event": "daily_summary_generated",
            "tenantId": summary["tenantId"],
            "tenantSlug": tenant.get("slug", ""),
            "date": summary["summaryDate"],
            "summaryHeadline": summary["headline"],
            "metrics": summary["metrics"],
        },
        "whatsapp": {
            "channel": "whatsapp_hook",
            "template": "bizxus_daily_summary_v1",
            "recipientHint": (tenant.get("contact") or {}).get("whatsapp") or (tenant.get("contact") or {}).get("phone") or "",
            "payload": {
                "date": summary["summaryDate"],
                "headline": summary["headline"],
                "keyMetrics": summary["metrics"],
            },
        },
        "sms": {
            "channel": "sms_hook",
            "template": "bizxus_daily_sms_v1",
            "recipientHint": (tenant.get("contact") or {}).get("phone") or "",
            "payload": {
                "date": summary["summaryDate"],
                "headline": summary["headline"][:120],
            },
        },
    }


async def generate_daily_summary(tenant_id: str, user: dict, summary_date: str | None = None) -> dict:
    db = get_database()
    _, tenant = await _get_reporting_access(tenant_id, user)
    tenant_oid = tenant["_id"]
    timezone_name = await _report_timezone(db, tenant)
    target_day = _parse_summary_date(summary_date, timezone_name)
    start = target_day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    await sync_low_stock_notifications(tenant_oid)
    analytics = await get_analytics_summary(tenant_id, user)
    day_filter = {"tenantId": tenant_oid, "createdAt": {"$gte": start, "$lt": end}}
    order_filter = {**day_filter, "transactionType": "order", "status": {"$nin": ["cancelled", "rejected"]}}
    revenue_rows = await db.transactions.aggregate([
        {"$match": order_filter},
        {"$group": {"_id": None, "grossRevenue": {"$sum": "$pricing.total"}, "averageOrderValue": {"$avg": "$pricing.total"}}},
    ]).to_list(length=1)
    daily_revenue = revenue_rows[0] if revenue_rows else {}
    top_rows = await db.transactions.aggregate([
        {"$match": order_filter}, {"$unwind": "$items"},
        {"$group": {"_id": "$items.itemId", "name": {"$first": "$items.name"}, "quantity": {"$sum": "$items.quantity"}, "revenue": {"$sum": "$items.subtotal"}}},
        {"$sort": {"revenue": -1, "quantity": -1}}, {"$limit": 5},
    ]).to_list(length=5)
    daily_top_items = [{**serialize_document(row), "itemId": str(row.get("_id", ""))} for row in top_rows]
    daily_recent = [serialize_document(row) async for row in db.transactions.find(day_filter).sort("createdAt", -1).limit(5)]

    new_transactions = await db.transactions.count_documents({"tenantId": tenant_oid, "createdAt": {"$gte": start, "$lt": end}})
    new_orders = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "order", "createdAt": {"$gte": start, "$lt": end}})
    new_quotes = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "quote_request", "createdAt": {"$gte": start, "$lt": end}})
    new_bookings = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "booking_request", "createdAt": {"$gte": start, "$lt": end}})
    new_inquiries = await db.transactions.count_documents({"tenantId": tenant_oid, "transactionType": "inquiry", "createdAt": {"$gte": start, "$lt": end}})
    unread_alerts = await db.business_notifications.count_documents({"tenantId": tenant_oid, "status": "unread"})
    low_stock_count = await db.business_notifications.count_documents({"tenantId": tenant_oid, "type": "stock_alert"})

    headline = (
        f"{tenant.get('name', 'Business')} handled {new_transactions} new transactions on {start.strftime('%Y-%m-%d')}."
        if new_transactions
        else f"{tenant.get('name', 'Business')} had no new transactions on {start.strftime('%Y-%m-%d')}."
    )
    summary = {
        "tenantId": str(tenant_oid),
        "summaryDate": start.strftime("%Y-%m-%d"),
        "summaryTimezone": timezone_name,
        "headline": headline,
        "metrics": {
            "newTransactions": new_transactions,
            "newOrders": new_orders,
            "newQuotes": new_quotes,
            "newBookings": new_bookings,
            "newInquiries": new_inquiries,
            "unreadAlerts": unread_alerts,
            "lowStockAlerts": low_stock_count,
            "grossRevenue": round(float(daily_revenue.get("grossRevenue", 0) or 0), 2),
            "averageOrderValue": round(float(daily_revenue.get("averageOrderValue", 0) or 0), 2),
        },
        "analyticsSummary": headline,
        "topItems": daily_top_items,
        "recentTransactions": daily_recent,
        "lowStockItems": analytics.get("lowStockItems", [])[:5],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    summary["hookPreview"] = _build_hook_preview(summary, tenant)

    now = datetime.now(timezone.utc)
    await db.report_snapshots.update_one(
        {"tenantId": tenant_oid, "reportType": "daily_summary", "summaryDate": summary["summaryDate"]},
        {
            "$set": {
                "summaryVersion": 2,
                "summaryTimezone": timezone_name,
                "headline": summary["headline"],
                "metrics": summary["metrics"],
                "analyticsSummary": summary["analyticsSummary"],
                "topItems": summary["topItems"],
                "recentTransactions": summary["recentTransactions"],
                "lowStockItems": summary["lowStockItems"],
                "hookPreview": summary["hookPreview"],
                "updatedAt": now,
            },
            "$setOnInsert": {
                "tenantId": tenant_oid,
                "reportType": "daily_summary",
                "summaryDate": summary["summaryDate"],
                "createdAt": now,
            },
        },
        upsert=True,
    )

    await create_business_notification(
        tenant_oid,
        "daily_summary",
        f"Daily summary ready for {summary['summaryDate']}",
        headline,
        priority="low",
        metadata={"summaryDate": summary["summaryDate"], "reportType": "daily_summary"},
        source_key=f"daily_summary:{summary['summaryDate']}",
    )
    return summary


async def get_daily_summary(tenant_id: str, user: dict, summary_date: str | None = None) -> dict:
    db = get_database()
    _, tenant = await _get_reporting_access(tenant_id, user)
    timezone_name = await _report_timezone(db, tenant)
    target_day = _parse_summary_date(summary_date, timezone_name)
    date_key = target_day.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d")
    snapshot = await db.report_snapshots.find_one({"tenantId": tenant["_id"], "reportType": "daily_summary", "summaryDate": date_key})
    if snapshot and snapshot.get("summaryVersion") == 2 and snapshot.get("summaryTimezone") == timezone_name:
        serialized = serialize_document(snapshot)
        serialized["tenantId"] = str(tenant["_id"])
        serialized["generatedAt"] = serialized.get("updatedAt") or serialized.get("createdAt")
        return serialized
    return await generate_daily_summary(tenant_id, user, date_key)
