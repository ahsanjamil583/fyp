from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument

from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
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
    result = await db.whatsapp_message_logs.update_one(
        {"_id": message_oid, "tenantId": tenant_oid, "deliveryStatus": "sending"},
        {"$set": {"deliveryStatus": delivery_status, "updatedAt": now}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=409, detail="Message is not awaiting delivery confirmation.")
    await db.report_delivery_logs.update_many(
        {"tenantId": tenant_oid, "providerLogId": str(message_oid)},
        {"$set": {"deliveryStatus": delivery_status, "updatedAt": now}},
    )
    return {"deliveryStatus": delivery_status}
