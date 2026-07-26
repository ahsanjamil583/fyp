from datetime import datetime, timezone

from bson import ObjectId

from app.core.object_ids import serialize_document
from app.db.mongodb import get_database


async def create_customer_notification(
    customer_user_id: ObjectId,
    tenant_id: ObjectId | None,
    notification_type: str,
    title: str,
    message: str,
    metadata: dict | None = None,
) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    notification = {
        "customerUserId": customer_user_id,
        "tenantId": tenant_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "metadata": metadata or {},
        "status": "unread",
        "createdAt": now,
        "updatedAt": now,
    }
    notification["_id"] = (await db.customer_notifications.insert_one(notification)).inserted_id
    return notification


async def list_customer_notifications(current_user: dict, page: int = 1, limit: int = 20) -> dict:
    db = get_database()
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    query = {"customerUserId": current_user["_id"]}
    total = await db.customer_notifications.count_documents(query)
    unread = await db.customer_notifications.count_documents({**query, "status": "unread"})
    cursor = (
        db.customer_notifications.find(query)
        .sort("createdAt", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    items = []
    async for notification in cursor:
        tenant = await db.tenants.find_one({"_id": notification.get("tenantId")}) if notification.get("tenantId") else None
        serialized = serialize_document(notification)
        serialized["tenant"] = serialize_document(tenant) if tenant else None
        items.append(serialized)
    return {
        "items": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit,
            "unread": unread,
        },
    }


async def mark_customer_notification_read(notification_id: str, current_user: dict) -> dict | None:
    db = get_database()
    from app.core.object_ids import parse_object_id

    notification_oid = parse_object_id(notification_id, "notificationId")
    await db.customer_notifications.update_one(
        {"_id": notification_oid, "customerUserId": current_user["_id"]},
        {"$set": {"status": "read", "updatedAt": datetime.now(timezone.utc)}},
    )
    updated = await db.customer_notifications.find_one({"_id": notification_oid, "customerUserId": current_user["_id"]})
    return serialize_document(updated) if updated else None


async def mark_all_customer_notifications_read(current_user: dict) -> dict:
    db = get_database()
    result = await db.customer_notifications.update_many(
        {"customerUserId": current_user["_id"], "status": "unread"},
        {"$set": {"status": "read", "updatedAt": datetime.now(timezone.utc)}},
    )
    return {"updatedCount": result.modified_count}
