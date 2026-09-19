import logging
from datetime import datetime, timedelta, timezone
import re

from fastapi import HTTPException, status

from app.core.item_views import customer_item_view
from app.core.public_views import public_business_view, customer_order_view
from app.core.object_ids import parse_object_id, serialize_document
from app.db.mongodb import get_database
from app.services.category_config_service import validate_tenant_fulfillment
from app.services.business_notification_service import create_business_notification
from app.services.custom_field_service import validate_custom_values_for_tenant_oid
from app.services.customer_service import sync_customer_stats_for_transaction
from app.services.inventory_service import reserve_transaction_stock
from app.services.localization_service import normalize_optional_email, normalize_optional_pk_phone
from app.services.order_message_service import notify_order_placed
from app.services.order_validation_service import normalize_fulfillment, normalize_notes
from app.services.payment_service import get_customer_payment_options_for_tenant, normalize_customer_payment_preference
from app.services.smart_order_service import claim_order_submission, resolve_requested_order_items
from app.services.transaction_number_service import generate_transaction_number
from app.services.transaction_workflow_service import (
    get_initial_payment_status,
    get_initial_transaction_status,
    infer_transaction_type,
    normalize_transaction_type,
)
from app.services.whatsapp_service import get_customer_facing_whatsapp_agent

logger = logging.getLogger(__name__)


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
    serialized = public_business_view(tenant)
    serialized["paymentOptions"] = await get_customer_payment_options_for_tenant(tenant["_id"], allow_otp=False)
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
        search = re.escape(search[:200])
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
        "items": [customer_item_view(item) async for item in cursor],
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
    return customer_item_view(item)


# How many unconfirmed website orders one anonymous phone number may hold against a
# single business at a time. This endpoint needs no account, and every order it creates
# reserves real stock, so without a ceiling one script can tie up a shop's entire
# inventory in orders nobody intends to collect. Genuine customers place one order and
# wait; they do not stack five pending ones.
MAX_OPEN_ANONYMOUS_ORDERS_PER_PHONE = 3
ANONYMOUS_ORDER_WINDOW_HOURS = 24


async def _guard_anonymous_order_volume(db, tenant: dict, payload) -> None:
    """Refuse a further anonymous order once this phone already has several open.

    The generic rate limiter caps requests per minute, which does not stop a slow
    trickle of orders from accumulating reservations over hours.
    """
    # Same normaliser the snapshot is written with, or the lookup never matches.
    try:
        phone = normalize_optional_pk_phone(getattr(payload, "customerPhone", "") or "")
    except HTTPException:
        return
    if not phone:
        return
    since = datetime.now(timezone.utc) - timedelta(hours=ANONYMOUS_ORDER_WINDOW_HOURS)
    open_orders = await db.transactions.count_documents(
        {
            "tenantId": tenant["_id"],
            "source": "website",
            "customerUserId": None,
            "customerSnapshot.phone": phone,
            "status": {"$in": ["pending", "awaiting_confirmation", "submitted", "new"]},
            "createdAt": {"$gte": since},
        }
    )
    if open_orders >= MAX_OPEN_ANONYMOUS_ORDERS_PER_PHONE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "There are already several open orders against this phone number. "
                "Please wait for the business to confirm them before placing another."
            ),
        )


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
    await _guard_anonymous_order_volume(db, tenant, payload)
    # No cart exists here to claim, so the submission itself is claimed. Without this a
    # double POST created two orders and reserved the stock twice.
    await claim_order_submission(
        db,
        tenant["_id"],
        [
            str(getattr(payload, "customerPhone", "") or ""),
            str(getattr(payload, "customerEmail", "") or ""),
            str(subtotal),
            *(f"{line.get('itemId')}x{line.get('quantity')}" for line in transaction_items),
        ],
    )

    requested_transaction_type = normalize_transaction_type(getattr(payload, "transactionType", None))
    transaction_type = infer_transaction_type(requested_transaction_type, resolved_items)
    payment_options = await get_customer_payment_options_for_tenant(tenant["_id"], allow_otp=False)
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
    # Everything past this point is a side effect. The order exists and its stock is
    # reserved, so a failure here must not surface as an error to a caller whose order
    # was actually placed - they retry, and the stock is reserved twice.
    try:
        transaction["customerId"] = await sync_customer_stats_for_transaction(tenant, transaction)
    except Exception:
        logger.exception("Customer stats sync failed for %s.", transaction.get("transactionNumber"))
    try:
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
        # A guest order has only the snapshot name/phone/email, which is exactly what the
        # confirmation resolves against.
        await notify_order_placed(transaction, tenant)

        if getattr(payload, "conversationId", None):
            # Website chat identifies a conversation by its opaque session token, not by ObjectId.
            await db.conversations.update_one(
                {"publicSessionToken": str(payload.conversationId).strip(), "tenantId": tenant["_id"], "channel": "website"},
                {"$set": {"pendingOrderDraft": {}, "summary": f"Draft confirmed as {transaction['transactionNumber']}.", "updatedAt": now, "lastMessageAt": now}},
            )
    except Exception:
        logger.exception("Post-order steps failed for %s.", transaction.get("transactionNumber"))
    return customer_order_view(transaction)


async def create_public_order(slug: str, payload) -> dict:
    return await create_public_transaction(slug, payload)
