from datetime import datetime, timezone
import re

from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.business_notification_service import create_business_notification
from app.services.customer_notification_service import create_customer_notification
from app.services.customer_service import sync_customer_stats_for_transaction
from app.services.inventory_service import apply_transaction_inventory_transition, get_inventory_movements_for_transaction, restore_transaction_stock
from app.services.payment_service import summarize_payment_records_for_transaction
from app.services.transaction_workflow_service import (
    ALLOWED_TRANSACTION_TYPES,
    get_allowed_payment_statuses,
    get_allowed_statuses,
    validate_payment_status,
    validate_transaction_status,
)


async def _ensure_transaction_access(tenant_id: str, user: dict):
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    return tenant_oid, tenant


async def list_transactions(
    tenant_id: str,
    user: dict,
    search: str = "",
    status_filter: str | None = None,
    transaction_type: str | None = None,
    source_filter: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict:
    db = get_database()
    tenant_oid, _ = await _ensure_transaction_access(tenant_id, user)
    page = max(page, 1)
    limit = min(max(limit, 1), 100)

    query = {"tenantId": tenant_oid}
    if status_filter:
        query["status"] = status_filter
    if transaction_type:
        if transaction_type not in ALLOWED_TRANSACTION_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid transaction type.")
        query["transactionType"] = transaction_type
    if source_filter:
        query["source"] = source_filter
    if search:
        search = re.escape(search[:200])
        query["$or"] = [
            {"transactionNumber": {"$regex": search, "$options": "i"}},
            {"customerSnapshot.name": {"$regex": search, "$options": "i"}},
            {"customerSnapshot.phone": {"$regex": search, "$options": "i"}},
            {"customerSnapshot.email": {"$regex": search, "$options": "i"}},
            {"items.name": {"$regex": search, "$options": "i"}},
        ]

    total = await db.transactions.count_documents(query)
    cursor = db.transactions.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    items = []
    async for transaction in cursor:
        item = serialize_document(transaction)
        item["statusOptions"] = get_allowed_statuses(item.get("transactionType", "order"))
        item["paymentStatusOptions"] = get_allowed_payment_statuses(item.get("transactionType", "order"))
        item["paymentProofSummary"] = await summarize_payment_records_for_transaction(transaction, db=db)
        items.append(item)

    summary_pipeline = [
        {"$match": {"tenantId": tenant_oid}},
        {"$group": {"_id": "$transactionType", "count": {"$sum": 1}}},
    ]
    status_pipeline = [
        {"$match": {"tenantId": tenant_oid}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    inventory_pipeline = [
        {"$match": {"tenantId": tenant_oid}},
        {"$group": {"_id": "$inventoryStatus", "count": {"$sum": 1}}},
    ]
    type_counts = {row["_id"]: row["count"] for row in await db.transactions.aggregate(summary_pipeline).to_list(length=None)}
    status_counts = {row["_id"]: row["count"] for row in await db.transactions.aggregate(status_pipeline).to_list(length=None)}
    inventory_counts = {row["_id"] or "unknown": row["count"] for row in await db.transactions.aggregate(inventory_pipeline).to_list(length=None)}
    source_values = await db.transactions.distinct("source", {"tenantId": tenant_oid})

    return {
        "items": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit,
        },
        "summary": {
            "totalTransactions": sum(type_counts.values()),
            "byType": type_counts,
            "byStatus": status_counts,
            "byInventoryStatus": inventory_counts,
        },
        "filters": {
            "transactionTypes": sorted(ALLOWED_TRANSACTION_TYPES),
            "statuses": sorted(status_counts.keys()),
            "sources": sorted(source_values),
        },
    }


async def update_transaction(tenant_id: str, transaction_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _ensure_transaction_access(tenant_id, user)
    transaction_oid = parse_object_id(transaction_id, "transactionId")
    existing = await db.transactions.find_one({"_id": transaction_oid, "tenantId": tenant_oid})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")

    transaction_type = existing.get("transactionType", "order")
    updates = {}
    history_entries = []
    now = datetime.now(timezone.utc)

    if payload.status is not None:
        new_status = validate_transaction_status(transaction_type, payload.status)
        if new_status != existing.get("status"):
            updates["status"] = new_status
            history_entries.append(
                {
                    "field": "status",
                    "from": existing.get("status"),
                    "to": new_status,
                    "note": payload.internalNotes.strip(),
                    "changedAt": now,
                    "changedByUserId": user["_id"],
                }
            )

    if payload.paymentStatus is not None:
        new_payment_status = validate_payment_status(transaction_type, payload.paymentStatus)
        if new_payment_status != existing.get("paymentStatus"):
            updates["paymentStatus"] = new_payment_status
            history_entries.append(
                {
                    "field": "paymentStatus",
                    "from": existing.get("paymentStatus"),
                    "to": new_payment_status,
                    "note": payload.internalNotes.strip(),
                    "changedAt": now,
                    "changedByUserId": user["_id"],
                }
            )

    if not updates:
        return serialize_document(existing)

    updates["updatedAt"] = now
    if payload.internalNotes.strip():
        updates["internalNotes"] = payload.internalNotes.strip()

    update_doc = {"$set": updates}
    if history_entries:
        update_doc["$push"] = {"statusHistory": {"$each": history_entries}}
    update_doc["$set"]["workflowOperation"] = "updating"
    result = await db.transactions.update_one(
        {"_id": transaction_oid, "tenantId": tenant_oid, "status": existing.get("status"), "paymentStatus": existing.get("paymentStatus"), "workflowOperation": {"$exists": False}, "inventoryOperation": {"$exists": False}},
        update_doc,
    )
    if not result.matched_count:
        raise HTTPException(status_code=409, detail="This transaction changed or is being updated. Please reload.")
    try:
        updated = await db.transactions.find_one({"_id": transaction_oid, "tenantId": tenant_oid})
        if updated and any(entry["field"] == "status" for entry in history_entries):
            updated = await apply_transaction_inventory_transition(existing, updated, user.get("_id"))
        if updated and any(entry["field"] == "paymentStatus" and entry["to"] == "refunded" for entry in history_entries):
            updated = await restore_transaction_stock(updated, user.get("_id"))
    except Exception:
        rollback = {key: existing.get(key) for key in updates if key not in {"workflowOperation", "updatedAt"}}
        await db.transactions.update_one(
            {"_id": transaction_oid, "workflowOperation": "updating"},
            {"$set": rollback, "$pull": {"statusHistory": {"changedAt": now}}},
        )
        raise
    finally:
        await db.transactions.update_one({"_id": transaction_oid}, {"$unset": {"workflowOperation": ""}})
    if updated and updated.get("customerId"):
        await sync_customer_stats_for_transaction(tenant, updated)
        updated = await db.transactions.find_one({"_id": transaction_oid, "tenantId": tenant_oid})
    if updated and updated.get("customerUserId") and history_entries:
        changed_fields = ", ".join(entry["field"] for entry in history_entries)
        await create_customer_notification(
            updated["customerUserId"],
            tenant_oid,
            "transaction_updated",
            f"{updated.get('transactionNumber', 'Transaction')} updated",
            f"{tenant.get('name', 'A business')} updated your {updated.get('transactionType', 'transaction').replace('_', ' ')} {changed_fields}.",
            {
                "transactionId": str(updated["_id"]),
                "transactionType": updated.get("transactionType", "order"),
                "tenantSlug": tenant.get("slug", ""),
                "fields": [entry["field"] for entry in history_entries],
            },
        )
    if updated and history_entries:
        changed_fields = [entry["field"] for entry in history_entries]
        await create_business_notification(
            tenant_oid,
            "transaction_update",
            f"{updated.get('transactionNumber', 'Transaction')} updated",
            f"{updated.get('transactionType', 'transaction').replace('_', ' ').title()} updated: {', '.join(changed_fields)}.",
            priority="medium",
            # One notification per transaction per status, collapsing the burst an owner
            # sees when they move an order through several states in a row.
            source_key=f"txn_update:{updated['_id']}:{updated.get('status', '')}",
            metadata={
                "transactionId": str(updated["_id"]),
                "transactionNumber": updated.get("transactionNumber", ""),
                "transactionType": updated.get("transactionType", ""),
                "fields": changed_fields,
                "tenantSlug": tenant.get("slug", ""),
            },
        )
    serialized = serialize_document(updated)
    serialized["inventoryMovementsDetailed"] = await get_inventory_movements_for_transaction(tenant_oid, transaction_oid)
    serialized["statusOptions"] = get_allowed_statuses(transaction_type)
    serialized["paymentStatusOptions"] = get_allowed_payment_statuses(transaction_type)
    serialized["paymentProofSummary"] = await summarize_payment_records_for_transaction(updated, db=db)
    return serialized
