from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database

LOW_STOCK_SOURCE_PREFIX = "low_stock"


def _normalize_priority(priority: str | None) -> str:
    normalized = str(priority or "medium").strip().lower()
    return normalized if normalized in {"low", "medium", "high"} else "medium"


def _build_hook_preview(notification: dict, tenant: dict) -> dict:
    event = {
        "event": notification.get("type", "notification"),
        "tenantId": str(notification.get("tenantId", "")),
        "tenantSlug": tenant.get("slug", ""),
        "tenantName": tenant.get("name", ""),
        "title": notification.get("title", ""),
        "message": notification.get("message", ""),
        "priority": notification.get("priority", "medium"),
        "metadata": notification.get("metadata", {}) or {},
        "createdAt": notification.get("createdAt").isoformat() if notification.get("createdAt") else None,
    }
    return {
        "webhookEvent": event,
        "whatsapp": {
            "channel": "whatsapp_hook",
            "template": "bizxus_owner_alert_v1",
            "recipientHint": (tenant.get("contact") or {}).get("whatsapp") or (tenant.get("contact") or {}).get("phone") or "",
            "payload": {
                "title": event["title"],
                "body": event["message"],
                "tenantSlug": event["tenantSlug"],
                "eventType": event["event"],
            },
        },
        "sms": {
            "channel": "sms_hook",
            "template": "bizxus_owner_sms_v1",
            "recipientHint": (tenant.get("contact") or {}).get("phone") or "",
            "payload": {
                "title": event["title"][:80],
                "body": event["message"][:160],
                "eventType": event["event"],
            },
        },
    }


async def _get_tenant_with_notifications_access(tenant_id: str, user: dict) -> tuple[ObjectId, dict]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "notifications")
    return tenant_oid, tenant


async def create_business_notification(
    tenant_id: ObjectId,
    notification_type: str,
    title: str,
    message: str,
    *,
    priority: str = "medium",
    metadata: dict | None = None,
    source_key: str | None = None,
) -> dict:
    db = get_database()
    tenant = await db.tenants.find_one({"_id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    now = datetime.now(timezone.utc)
    notification = {
        "tenantId": tenant_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "priority": _normalize_priority(priority),
        "status": "unread",
        "metadata": metadata or {},
        "createdAt": now,
        "updatedAt": now,
    }
    if source_key:
        notification["sourceKey"] = source_key
    notification["hookPreview"] = _build_hook_preview(notification, tenant)

    if source_key:
        await db.business_notifications.update_one(
            {"tenantId": tenant_id, "sourceKey": source_key},
            {
                "$set": {
                    "type": notification["type"],
                    "title": notification["title"],
                    "message": notification["message"],
                    "priority": notification["priority"],
                    "status": "unread",
                    "metadata": notification["metadata"],
                    "hookPreview": notification["hookPreview"],
                    "updatedAt": now,
                },
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
        )
        stored = await db.business_notifications.find_one({"tenantId": tenant_id, "sourceKey": source_key})
        return serialize_document(stored)

    notification["_id"] = (await db.business_notifications.insert_one(notification)).inserted_id
    return serialize_document(notification)


async def sync_low_stock_notifications(tenant_id: ObjectId) -> dict:
    db = get_database()
    tenant = await db.tenants.find_one({"_id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    low_stock_items = await db.items.find(
        {
            "tenantId": tenant_id,
            "status": "active",
            "isStockTracked": True,
            "$expr": {"$lte": ["$stock.quantity", "$stock.lowStockThreshold"]},
        }
    ).to_list(length=100)

    active_source_keys = set()
    for item in low_stock_items:
        source_key = f"{LOW_STOCK_SOURCE_PREFIX}:{item['_id']}"
        active_source_keys.add(source_key)
        quantity = ((item.get("stock") or {}).get("quantity")) or 0
        threshold = ((item.get("stock") or {}).get("lowStockThreshold")) or 0
        await create_business_notification(
            tenant_id,
            "stock_alert",
            f"Low stock: {item.get('name', 'Item')}",
            f"{item.get('name', 'Item')} is at {quantity} units, below the threshold of {threshold}.",
            priority="high" if quantity <= 0 else "medium",
            metadata={
                "itemId": str(item["_id"]),
                "itemName": item.get("name", ""),
                "quantity": quantity,
                "threshold": threshold,
                "tenantSlug": tenant.get("slug", ""),
            },
            source_key=source_key,
        )

    stale_cursor = db.business_notifications.find(
        {
            "tenantId": tenant_id,
            "type": "stock_alert",
            "sourceKey": {"$regex": f"^{LOW_STOCK_SOURCE_PREFIX}:"},
        }
    )
    cleared = 0
    async for row in stale_cursor:
        if row.get("sourceKey") not in active_source_keys:
            cleared += 1
            await db.business_notifications.delete_one({"_id": row["_id"]})

    return {"activeLowStockAlerts": len(active_source_keys), "clearedAlerts": cleared}


async def list_business_notifications(
    tenant_id: str,
    user: dict,
    *,
    page: int = 1,
    limit: int = 20,
    notification_type: str | None = None,
    status_filter: str | None = None,
) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_with_notifications_access(tenant_id, user)
    await sync_low_stock_notifications(tenant_oid)

    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    query = {"tenantId": tenant_oid}
    if notification_type:
        query["type"] = notification_type
    if status_filter:
        query["status"] = status_filter

    total = await db.business_notifications.count_documents(query)
    unread = await db.business_notifications.count_documents({**query, "status": "unread"})
    cursor = (
        db.business_notifications.find(query)
        .sort([("priority", 1), ("createdAt", -1)])
        .skip((page - 1) * limit)
        .limit(limit)
    )
    items = []
    async for notification in cursor:
        serialized = serialize_document(notification)
        serialized["tenant"] = {"id": str(tenant["_id"]), "name": tenant.get("name", ""), "slug": tenant.get("slug", "")}
        items.append(serialized)

    available_types = await db.business_notifications.distinct("type", {"tenantId": tenant_oid})
    return {
        "items": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit,
            "unread": unread,
        },
        "filters": {
            "types": sorted(available_types),
            "statuses": ["read", "unread"],
        },
    }


async def mark_business_notification_read(tenant_id: str, notification_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, _ = await _get_tenant_with_notifications_access(tenant_id, user)
    notification_oid = parse_object_id(notification_id, "notificationId")
    await db.business_notifications.update_one(
        {"_id": notification_oid, "tenantId": tenant_oid},
        {"$set": {"status": "read", "updatedAt": datetime.now(timezone.utc)}},
    )
    updated = await db.business_notifications.find_one({"_id": notification_oid, "tenantId": tenant_oid})
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    return serialize_document(updated)


async def mark_all_business_notifications_read(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, _ = await _get_tenant_with_notifications_access(tenant_id, user)
    result = await db.business_notifications.update_many(
        {"tenantId": tenant_oid, "status": "unread"},
        {"$set": {"status": "read", "updatedAt": datetime.now(timezone.utc)}},
    )
    return {"updatedCount": result.modified_count}
