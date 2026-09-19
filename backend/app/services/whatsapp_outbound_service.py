from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument

from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id
from app.integrations.whatsapp.provider import OTP_REDACTED_TEXT
from app.db.mongodb import get_database


async def _authorize(tenant_id, token):
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    db = get_database()
    if not token or not await db.whatsapp_integrations.find_one({"tenantId": tenant_oid, "bridgeToken": token, "provider": "baileys", "isConnected": True}):
        raise HTTPException(status_code=401, detail="Invalid WhatsApp bridge token or tenant.")
    tenant = await db.tenants.find_one({"_id": tenant_oid, "status": "active"})
    if not tenant:
        raise HTTPException(status_code=403, detail="Business is not active.")
    await ensure_tenant_module_enabled(tenant_oid, "whatsapp_agent")
    return db, tenant_oid


async def claim_outbound_message(tenant_id, token):
    db, tenant_oid = await _authorize(tenant_id, token)
    message = await db.whatsapp_message_logs.find_one_and_update(
        {"tenantId": tenant_oid, "provider": "baileys", "direction": "outbound", "deliveryStatus": "queued"},
        {"$set": {"deliveryStatus": "sending", "updatedAt": datetime.now(timezone.utc)}},
        sort=[("createdAt", 1)], return_document=ReturnDocument.AFTER,
    )
    if not message:
        return None
    return {"id": str(message["_id"]), "toPhone": message["toPhone"], "messageText": message["messageText"]}


async def acknowledge_outbound_message(tenant_id, message_id, token, delivery_status):
    db, tenant_oid = await _authorize(tenant_id, token)
    message_oid = parse_object_id(message_id, "messageId")
    now = datetime.now(timezone.utc)
    # The OTP code has now left the building, so it must not stay in the log. The row
    # is kept for support (recipient, status, timing); only the body goes.
    acknowledged = await db.whatsapp_message_logs.find_one({"_id": message_oid, "tenantId": tenant_oid})
    update = {"deliveryStatus": delivery_status, "updatedAt": now}
    if str(((acknowledged or {}).get("rawContext") or {}).get("source") or "").lower() == "otp":
        update["messageText"] = OTP_REDACTED_TEXT
    result = await db.whatsapp_message_logs.update_one(
        {"_id": message_oid, "tenantId": tenant_oid, "deliveryStatus": "sending"},
        {"$set": update},
    )
    if not result.matched_count:
        raise HTTPException(status_code=409, detail="Message is not awaiting delivery confirmation.")
    await db.report_delivery_logs.update_many(
        {"tenantId": tenant_oid, "providerLogId": str(message_oid)},
        {"$set": {"deliveryStatus": delivery_status, "updatedAt": now}},
    )
    message = await db.whatsapp_message_logs.find_one({"_id": message_oid, "tenantId": tenant_oid})
    summary_date = ((message or {}).get("rawContext") or {}).get("summaryDate")
    if summary_date:
        logs = await db.report_delivery_logs.find({"tenantId": tenant_oid, "summaryDate": summary_date}).to_list(length=None)
        statuses = {row.get("deliveryStatus") for row in logs}
        aggregate_status = "queued" if statuses & {"queued", "sending"} else "partial_failed" if "failed" in statuses and "sent" in statuses else "failed" if "failed" in statuses else "delivered"
        await db.report_delivery_settings.update_one(
            {"tenantId": tenant_oid, "lastSummaryDate": summary_date},
            {"$set": {"lastDeliveryStatus": aggregate_status, "updatedAt": now}},
        )
        await db.report_delivery_runs.update_one(
            {"_id": f"{tenant_oid}:{summary_date}"},
            {"$set": {"status": aggregate_status, "finishedAt": now}},
        )
    return {"deliveryStatus": delivery_status}
