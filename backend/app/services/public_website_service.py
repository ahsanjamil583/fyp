from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.db.mongodb import get_database
from app.services.category_config_service import validate_tenant_fulfillment
from app.services.business_notification_service import create_business_notification
from app.services.custom_field_service import validate_custom_values_for_tenant_oid
from app.services.customer_service import sync_customer_stats_for_transaction
from app.services.inventory_service import reserve_transaction_stock
from app.services.localization_service import normalize_optional_email, normalize_optional_pk_phone
from app.services.order_validation_service import normalize_fulfillment, normalize_notes
from app.services.payment_service import get_customer_payment_options_for_tenant, normalize_customer_payment_preference
from app.services.smart_order_service import resolve_requested_order_items
from app.services.transaction_number_service import generate_transaction_number
from app.services.transaction_workflow_service import (
    get_initial_payment_status,
    get_initial_transaction_status,
    infer_transaction_type,
    normalize_transaction_type,
)
from app.services.whatsapp_service import get_customer_facing_whatsapp_agent


async def _get_published_tenant(slug: str) -> dict:
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


async def get_public_business(slug: str) -> dict:
    tenant = await _get_published_tenant(slug)
    serialized = serialize_document(tenant)
    serialized["paymentOptions"] = await get_customer_payment_options_for_tenant(tenant["_id"])
    serialized["whatsappAgent"] = await get_customer_facing_whatsapp_agent(tenant)
    return serialized


async def list_public_items(slug: str, search: str = "", item_type: str | None = None, page: int = 1, limit: int = 20) -> dict:
    db = get_database()
    tenant = await _get_published_tenant(slug)
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    query = {
        "tenantId": tenant["_id"],
        "status": "active",
        "$or": [{"isSellable": True}, {"isBookable": True}],
    }
    if item_type:
        query["itemType"] = item_type
    if search:
        query["$and"] = [
            {"$or": query.pop("$or")},
            {
                "$or": [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"description": {"$regex": search, "$options": "i"}},
                    {"tags": {"$regex": search, "$options": "i"}},
                ]
            },
        ]

    total = await db.items.count_documents(query)
    cursor = db.items.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    return {
        "items": [serialize_document(item) async for item in cursor],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit,
        },
    }


async def get_public_item(slug: str, item_id: str) -> dict:
    db = get_database()
    tenant = await _get_published_tenant(slug)
    item_oid = parse_object_id(item_id, "itemId")
    item = await db.items.find_one(
        {
            "_id": item_oid,
            "tenantId": tenant["_id"],
            "status": "active",
            "$or": [{"isSellable": True}, {"isBookable": True}],
        }
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public item not found.")
    return serialize_document(item)


async def create_public_transaction(slug: str, payload) -> dict:
    db = get_database()
    tenant = await _get_published_tenant(slug)
    now = datetime.now(timezone.utc)
    normalized_fulfillment = normalize_fulfillment(payload.fulfillment)
    validate_tenant_fulfillment(tenant, normalized_fulfillment)
    normalized_notes = normalize_notes(payload.notes)
    normalized_custom_fields = await validate_custom_values_for_tenant_oid(tenant["_id"], "transactions", "transaction", payload.customFields or {})
    if not normalized_custom_fields["valid"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=normalized_custom_fields["errors"])
    resolved_items, transaction_items, subtotal = await resolve_requested_order_items(tenant, payload.items or [], db)

    requested_transaction_type = normalize_transaction_type(getattr(payload, "transactionType", None))
    transaction_type = infer_transaction_type(requested_transaction_type, resolved_items)
    payment_options = await get_customer_payment_options_for_tenant(tenant["_id"])
    payment_preference = normalize_customer_payment_preference(getattr(payload, "paymentMethod", None), payment_options)

    transaction = {
        "tenantId": tenant["_id"],
        "branchId": None,
        "customerId": None,
        "customerUserId": None,
        "customerProfileId": None,
        "transactionType": transaction_type,
        "transactionNumber": await generate_transaction_number(tenant["_id"], transaction_type),
        "source": "website",
        "status": get_initial_transaction_status(transaction_type),
        "items": transaction_items,
        "pricing": {
            "subtotal": subtotal,
            "discount": 0,
            "tax": 0,
            "deliveryFee": 0,
            "total": subtotal,
        },
        "paymentStatus": get_initial_payment_status(transaction_type),
        "paymentSummary": {
            "total": subtotal,
            "paid": 0,
            "cod": 0,
            "pending": 0,
            "rejected": 0,
            "refunded": 0,
            "balance": subtotal,
        },
        "paymentPreference": payment_preference,
        "paymentInstructions": payment_options,
        "fulfillment": normalized_fulfillment,
        "customerSnapshot": {
            "name": payload.customerName,
            "phone": normalize_optional_pk_phone(payload.customerPhone),
            "email": normalize_optional_email(payload.customerEmail),
        },
        "notes": normalized_notes,
        "internalNotes": "",
        "customFields": normalized_custom_fields["values"],
        "statusHistory": [
            {
                "field": "status",
                "from": None,
                "to": get_initial_transaction_status(transaction_type),
                "note": "Created from public website.",
                "changedAt": now,
                "changedByUserId": None,
            }
        ],
        "createdBy": None,
        "createdAt": now,
        "updatedAt": now,
    }
    transaction["_id"] = (await db.transactions.insert_one(transaction)).inserted_id
    try:
        transaction = await reserve_transaction_stock(transaction, None)
    except Exception:
        await db.transactions.delete_one({"_id": transaction["_id"]})
        raise
    customer_id = await sync_customer_stats_for_transaction(tenant, transaction)
    transaction["customerId"] = customer_id
    await create_business_notification(
        tenant["_id"],
        "order_alert",
        f"New {transaction_type.replace('_', ' ')} {transaction['transactionNumber']}",
        f"{payload.customerName or 'A website visitor'} submitted a new {transaction_type.replace('_', ' ')} from the public website.",
        priority="high" if transaction_type == "order" else "medium",
        metadata={
            "transactionId": str(transaction["_id"]),
            "transactionNumber": transaction["transactionNumber"],
            "transactionType": transaction_type,
            "source": "website_ai_chat" if getattr(payload, "conversationId", None) else "website",
            "customerName": payload.customerName,
            "tenantSlug": tenant.get("slug", ""),
        },
    )
    if getattr(payload, "conversationId", None):
        conversation_oid = parse_object_id(payload.conversationId, "conversationId")
        await db.conversations.update_one(
            {"_id": conversation_oid, "tenantId": tenant["_id"], "channel": "website"},
            {"$set": {"pendingOrderDraft": {}, "summary": f"Draft confirmed as {transaction['transactionNumber']}.", "updatedAt": now, "lastMessageAt": now}},
        )
    return serialize_document(transaction)


async def create_public_order(slug: str, payload) -> dict:
    return await create_public_transaction(slug, payload)
