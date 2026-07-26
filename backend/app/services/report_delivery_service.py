from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.integrations.sms.provider import SmsSendError, send_sms_text
from app.integrations.whatsapp.provider import WhatsAppSendError, send_whatsapp_text
from app.schemas.report_delivery_schema import ReportDeliveryRequest, ReportDeliverySettingsRequest, ScheduledReportRunRequest
from app.services.business_notification_service import create_business_notification
from app.services.localization_service import get_language_mode
from app.services.reporting_service import generate_daily_summary
from app.services.whatsapp_service import normalize_phone


async def _get_delivery_access(tenant_id: str, user: dict) -> tuple[ObjectId, dict]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "reports")
    return tenant_oid, tenant


def _default_recipient(tenant: dict, channel: str) -> str:
    contact = tenant.get("contact") or {}
    if channel == "whatsapp":
        return normalize_phone(contact.get("whatsapp") or contact.get("phone") or "")
    return normalize_phone(contact.get("phone") or contact.get("whatsapp") or "")


def _serialize_settings(settings_doc: dict | None, tenant: dict) -> dict:
    contact = tenant.get("contact") or {}
    if not settings_doc:
        return {
            "enabled": True,
            "whatsappEnabled": bool(contact.get("whatsapp") or contact.get("phone")),
            "smsEnabled": False,
            "deliveryTime": "21:00",
            "timezone": "Asia/Karachi",
            "whatsappRecipient": _default_recipient(tenant, "whatsapp"),
            "smsRecipient": _default_recipient(tenant, "sms"),
            "languageMode": "auto",
            "includeLowStock": True,
            "includeTopItems": True,
            "includeRecentOrders": True,
            "lastDeliveredAt": None,
            "lastDeliveryStatus": "not_configured",
        }
    serialized = serialize_document(settings_doc)
    serialized.setdefault("whatsappRecipient", _default_recipient(tenant, "whatsapp"))
    serialized.setdefault("smsRecipient", _default_recipient(tenant, "sms"))
    return serialized


async def get_report_delivery_settings(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_delivery_access(tenant_id, user)
    settings_doc = await db.report_delivery_settings.find_one({"tenantId": tenant_oid})
    return {"tenant": serialize_document(tenant), "settings": _serialize_settings(settings_doc, tenant)}


async def update_report_delivery_settings(tenant_id: str, payload: ReportDeliverySettingsRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_delivery_access(tenant_id, user)
    now = datetime.now(timezone.utc)
    update_doc = {
        "tenantId": tenant_oid,
        "enabled": payload.enabled,
        "whatsappEnabled": payload.whatsappEnabled,
        "smsEnabled": payload.smsEnabled,
        "deliveryTime": _normalize_delivery_time(payload.deliveryTime),
        "timezone": payload.timezone.strip() or "Asia/Karachi",
        "whatsappRecipient": normalize_phone(payload.whatsappRecipient) or _default_recipient(tenant, "whatsapp"),
        "smsRecipient": normalize_phone(payload.smsRecipient) or _default_recipient(tenant, "sms"),
        "languageMode": _normalize_language_mode(payload.languageMode),
        "includeLowStock": payload.includeLowStock,
        "includeTopItems": payload.includeTopItems,
        "includeRecentOrders": payload.includeRecentOrders,
        "updatedAt": now,
    }
    await db.report_delivery_settings.update_one(
        {"tenantId": tenant_oid},
        {"$set": update_doc, "$setOnInsert": {"createdAt": now, "lastDeliveryStatus": "not_delivered"}},
        upsert=True,
    )
    settings_doc = await db.report_delivery_settings.find_one({"tenantId": tenant_oid})
    return {"tenant": serialize_document(tenant), "settings": _serialize_settings(settings_doc, tenant)}


def _normalize_delivery_time(value: str) -> str:
    value = str(value or "21:00").strip()
    try:
        hours, minutes = value.split(":", 1)
        hour_value = int(hours)
        minute_value = int(minutes)
        if 0 <= hour_value <= 23 and 0 <= minute_value <= 59:
            return f"{hour_value:02d}:{minute_value:02d}"
    except Exception:
        pass
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="deliveryTime must be HH:MM in 24-hour format.")


def _normalize_language_mode(value: str) -> str:
    normalized = str(value or "auto").strip().lower()
    return normalized if normalized in {"auto", "english", "roman_urdu", "mixed"} else "auto"


def _money(value) -> str:
    try:
        return f"PKR {float(value or 0):,.0f}"
    except Exception:
        return "PKR 0"


def _pick_language(settings_doc: dict | None, tenant: dict) -> str:
    configured = (settings_doc or {}).get("languageMode", "auto")
    if configured and configured != "auto":
        return configured
    return get_language_mode(tenant.get("settings"))


def build_daily_report_message(summary: dict, tenant: dict, settings_doc: dict | None = None, channel: str = "whatsapp") -> str:
    delivery_settings = _serialize_settings(settings_doc, tenant)
    language_mode = _pick_language(delivery_settings, tenant)
    metrics = summary.get("metrics") or {}
    top_items = summary.get("topItems") or []
    low_stock_items = summary.get("lowStockItems") or []
    recent_transactions = summary.get("recentTransactions") or []

    if language_mode == "roman_urdu":
        lines = [
            f"BizXus AI Daily Report - {tenant.get('name', 'Business')}",
            f"Date: {summary.get('summaryDate')}",
            f"Aaj total {metrics.get('newTransactions', 0)} transactions aur {metrics.get('newOrders', 0)} orders aaye.",
            f"Revenue: {_money(metrics.get('grossRevenue', 0))} | Avg order: {_money(metrics.get('averageOrderValue', 0))}",
        ]
        if delivery_settings.get("includeTopItems") and top_items:
            top = top_items[0]
            lines.append(f"Top item: {top.get('name', 'Item')} ({top.get('quantity', 0)} qty, {_money(top.get('revenue', 0))}).")
        if delivery_settings.get("includeLowStock"):
            if low_stock_items:
                names = ", ".join(item.get("name", "Item") for item in low_stock_items[:3])
                lines.append(f"Low stock alert: {names}. Reorder check kar lein.")
            else:
                lines.append("Low stock pressure nahi hai.")
        if delivery_settings.get("includeRecentOrders") and recent_transactions:
            lines.append(f"Latest: {recent_transactions[0].get('transactionNumber', 'Order')} - {recent_transactions[0].get('status', 'status')}.")
        lines.append("Dashboard me details review kar sakte hain.")
    else:
        lines = [
            f"BizXus AI Daily Report - {tenant.get('name', 'Business')}",
            f"Date: {summary.get('summaryDate')}",
            f"Today: {metrics.get('newTransactions', 0)} transactions, {metrics.get('newOrders', 0)} orders, {metrics.get('newQuotes', 0)} quotes, {metrics.get('newBookings', 0)} bookings.",
            f"Revenue: {_money(metrics.get('grossRevenue', 0))} | Average order: {_money(metrics.get('averageOrderValue', 0))}",
        ]
        if delivery_settings.get("includeTopItems") and top_items:
            top = top_items[0]
            lines.append(f"Top item: {top.get('name', 'Item')} ({top.get('quantity', 0)} qty, {_money(top.get('revenue', 0))}).")
        if delivery_settings.get("includeLowStock"):
            if low_stock_items:
                names = ", ".join(item.get("name", "Item") for item in low_stock_items[:3])
                lines.append(f"Low stock needs attention: {names}.")
            else:
                lines.append("No low-stock pressure right now.")
        if delivery_settings.get("includeRecentOrders") and recent_transactions:
            lines.append(f"Latest transaction: {recent_transactions[0].get('transactionNumber', 'Order')} - {recent_transactions[0].get('status', 'status')}.")
        lines.append("Open the dashboard for full details.")

    message = "\n".join(lines)
    if channel == "sms":
        return message[:600]
    return message[:3900]


async def deliver_daily_summary(tenant_id: str, payload: ReportDeliveryRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_delivery_access(tenant_id, user)
    settings_doc = await db.report_delivery_settings.find_one({"tenantId": tenant_oid})
    delivery_settings = _serialize_settings(settings_doc, tenant)
    summary = await generate_daily_summary(tenant_id, user, payload.summaryDate)
    requested_channels = [_normalize_channel(channel) for channel in payload.channels]
    requested_channels = [channel for channel in requested_channels if channel]
    if not requested_channels:
        requested_channels = ["whatsapp", "sms"]

    logs = []
    for channel in requested_channels:
        if channel == "whatsapp" and not delivery_settings.get("whatsappEnabled", True):
            logs.append(await _store_skipped_delivery(tenant_oid, summary, channel, "WhatsApp delivery is disabled in settings."))
            continue
        if channel == "sms" and not delivery_settings.get("smsEnabled", False):
            logs.append(await _store_skipped_delivery(tenant_oid, summary, channel, "SMS delivery is disabled in settings."))
            continue
        log = await _deliver_channel(
            tenant_oid=tenant_oid,
            tenant=tenant,
            summary=summary,
            settings_doc=delivery_settings,
            channel=channel,
            dry_run=payload.dryRun,
        )
        logs.append(log)

    status_value = "delivered"
    if any(log.get("deliveryStatus") == "failed" for log in logs):
        status_value = "partial_failed" if any(log.get("deliveryStatus") in {"sent", "mock_sent", "dry_run"} for log in logs) else "failed"
    elif all(log.get("deliveryStatus") in {"skipped"} for log in logs):
        status_value = "skipped"

    await db.report_delivery_settings.update_one(
        {"tenantId": tenant_oid},
        {
            "$set": {
                "lastDeliveredAt": datetime.now(timezone.utc),
                "lastDeliveryStatus": status_value,
                "lastSummaryDate": summary.get("summaryDate"),
                "updatedAt": datetime.now(timezone.utc),
            },
            "$setOnInsert": {"tenantId": tenant_oid, "createdAt": datetime.now(timezone.utc)},
        },
        upsert=True,
    )
    await create_business_notification(
        tenant_oid,
        "report_delivery",
        f"Daily report delivery {status_value.replace('_', ' ')}",
        f"Daily report for {summary.get('summaryDate')} delivery completed with status: {status_value}.",
        priority="low" if status_value in {"delivered", "skipped"} else "medium",
        metadata={"summaryDate": summary.get("summaryDate"), "channels": requested_channels, "status": status_value},
        source_key=f"report_delivery:{summary.get('summaryDate')}:{'-'.join(requested_channels)}",
    )
    return {"summary": summary, "deliveryStatus": status_value, "logs": [serialize_document(log) for log in logs]}


def _normalize_channel(channel: str) -> str:
    normalized = str(channel or "").strip().lower()
    return normalized if normalized in {"whatsapp", "sms"} else ""


async def _store_skipped_delivery(tenant_oid: ObjectId, summary: dict, channel: str, reason: str) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    log = {
        "tenantId": tenant_oid,
        "summaryDate": summary.get("summaryDate"),
        "channel": channel,
        "provider": "none",
        "recipient": "",
        "messageText": "",
        "deliveryStatus": "skipped",
        "error": reason,
        "createdAt": now,
        "updatedAt": now,
    }
    log["_id"] = (await db.report_delivery_logs.insert_one(log)).inserted_id
    return log


async def _deliver_channel(*, tenant_oid: ObjectId, tenant: dict, summary: dict, settings_doc: dict, channel: str, dry_run: bool) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    message_text = build_daily_report_message(summary, tenant, settings_doc, channel=channel)
    recipient = normalize_phone(settings_doc.get("whatsappRecipient") if channel == "whatsapp" else settings_doc.get("smsRecipient"))
    if not recipient:
        return await _store_failed_delivery(tenant_oid, summary, channel, message_text, "No recipient phone number configured.")

    base_log = {
        "tenantId": tenant_oid,
        "summaryDate": summary.get("summaryDate"),
        "channel": channel,
        "recipient": recipient,
        "messageText": message_text,
        "createdAt": now,
        "updatedAt": now,
    }
    if dry_run:
        base_log.update({"provider": "dry_run", "deliveryStatus": "dry_run", "providerLogId": "", "providerResponse": {"dryRun": True}})
        base_log["_id"] = (await db.report_delivery_logs.insert_one(base_log)).inserted_id
        return base_log

    try:
        if channel == "whatsapp":
            integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid, "isConnected": True})
            provider = (integration or {}).get("provider") or settings.whatsapp_provider
            provider_log = await send_whatsapp_text(
                tenant_id=tenant_oid,
                conversation_id=None,
                provider=provider,
                to_phone=recipient,
                message_text=message_text,
                integration=integration,
                raw_context={"source": "daily_report_delivery", "summaryDate": summary.get("summaryDate")},
            )
        else:
            provider_log = await send_sms_text(
                tenant_id=tenant_oid,
                provider=settings.sms_provider,
                to_phone=recipient,
                message_text=message_text,
                raw_context={"source": "daily_report_delivery", "summaryDate": summary.get("summaryDate")},
            )
        base_log.update(
            {
                "provider": provider_log.get("provider", channel),
                "deliveryStatus": provider_log.get("deliveryStatus", "sent"),
                "providerLogId": str(provider_log.get("_id", "")),
                "providerResponse": provider_log.get("providerResponse", {}),
            }
        )
    except (WhatsAppSendError, SmsSendError) as exc:
        base_log.update({"provider": channel, "deliveryStatus": "failed", "error": str(exc)})
    base_log["_id"] = (await db.report_delivery_logs.insert_one(base_log)).inserted_id
    return base_log


async def _store_failed_delivery(tenant_oid: ObjectId, summary: dict, channel: str, message_text: str, error: str) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    log = {
        "tenantId": tenant_oid,
        "summaryDate": summary.get("summaryDate"),
        "channel": channel,
        "provider": channel,
        "recipient": "",
        "messageText": message_text,
        "deliveryStatus": "failed",
        "error": error,
        "createdAt": now,
        "updatedAt": now,
    }
    log["_id"] = (await db.report_delivery_logs.insert_one(log)).inserted_id
    return log


async def list_report_delivery_logs(tenant_id: str, user: dict, *, limit: int = 20) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_delivery_access(tenant_id, user)
    limit = min(max(limit, 1), 100)
    cursor = db.report_delivery_logs.find({"tenantId": tenant_oid}).sort("createdAt", -1).limit(limit)
    logs = [serialize_document(row) async for row in cursor]
    return {"tenant": serialize_document(tenant), "items": logs}


async def run_scheduled_report_delivery(tenant_id: str, payload: ScheduledReportRunRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_delivery_access(tenant_id, user)
    settings_doc = await db.report_delivery_settings.find_one({"tenantId": tenant_oid})
    delivery_settings = _serialize_settings(settings_doc, tenant)
    if not delivery_settings.get("enabled", True):
        return {"deliveryStatus": "skipped", "reason": "Daily report delivery is disabled.", "logs": []}
    channels = []
    if delivery_settings.get("whatsappEnabled", True):
        channels.append("whatsapp")
    if delivery_settings.get("smsEnabled", False):
        channels.append("sms")
    if not channels:
        return {"deliveryStatus": "skipped", "reason": "No delivery channel is enabled.", "logs": []}
    return await deliver_daily_summary(tenant_id, ReportDeliveryRequest(summaryDate=payload.summaryDate, channels=channels, dryRun=payload.dryRun), user)
