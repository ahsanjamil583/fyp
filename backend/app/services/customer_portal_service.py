from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.db.mongodb import get_database
from app.services.ai_chat_service import clear_customer_conversation_draft
from app.services.custom_field_service import _list_custom_fields_for_tenant_oid
from app.services.category_config_service import validate_tenant_fulfillment
from app.services.business_notification_service import create_business_notification
from app.services.custom_field_service import validate_custom_values_for_tenant_oid
from app.services.customer_notification_service import create_customer_notification
from app.services.customer_service import ensure_customer_record_for_tenant, sync_customer_stats_for_transaction
from app.services.inventory_service import reserve_transaction_stock
from app.services.customer_portal_common_service import get_customer_profile_and_user, get_marketplace_tenant_or_404
from app.services.localization_service import normalize_optional_pk_phone_or_blank
from app.services.order_validation_service import normalize_fulfillment, normalize_notes
from app.services.payment_service import get_customer_payment_options_for_tenant, normalize_customer_payment_preference
from app.services.payment_service import list_customer_payment_records_for_transaction, summarize_payment_records_for_transaction
from app.services.smart_order_service import resolve_requested_order_items
from app.services.transaction_number_service import generate_transaction_number
from app.services.transaction_workflow_service import (
    get_initial_payment_status,
    get_initial_transaction_status,
    infer_transaction_type,
    normalize_transaction_type,
)
from app.services.whatsapp_service import get_customer_facing_whatsapp_agent


async def _get_customer_profile_and_user(current_user: dict) -> tuple[dict, str]:
    return await get_customer_profile_and_user(current_user)


async def _get_marketplace_tenant_or_404(slug: str) -> dict:
    return await get_marketplace_tenant_or_404(slug)


async def list_marketplace_businesses(search: str = "", city: str = "", category_id: str | None = None, page: int = 1, limit: int = 20) -> dict:
    db = get_database()
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    query = {
        "status": "active",
        "websiteStatus": "published",
        "settings.publicVisibility": True,
        "enabledModuleCodes": "customer_portal",
    }
    if city:
        query["address.city"] = {"$regex": city, "$options": "i"}
    if category_id:
        query["businessCategoryId"] = parse_object_id(category_id, "businessCategoryId")
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"address.city": {"$regex": search, "$options": "i"}},
        ]

    total = await db.tenants.count_documents(query)
    cursor = db.tenants.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    items = []
    async for tenant in cursor:
        serialized = serialize_document(tenant)
        serialized["whatsappAgent"] = await get_customer_facing_whatsapp_agent(tenant)
        items.append(serialized)
    return {
        "items": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit,
        },
    }


async def get_marketplace_business(slug: str) -> dict:
    tenant = await _get_marketplace_tenant_or_404(slug)
    serialized = serialize_document(tenant)
    serialized["paymentOptions"] = await get_customer_payment_options_for_tenant(tenant["_id"])
    serialized["whatsappAgent"] = await get_customer_facing_whatsapp_agent(tenant)
    return serialized


async def list_marketplace_items(slug: str, search: str = "", item_type: str | None = None, page: int = 1, limit: int = 20) -> dict:
    db = get_database()
    tenant = await _get_marketplace_tenant_or_404(slug)
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


async def get_marketplace_item(slug: str, item_id: str) -> dict:
    db = get_database()
    tenant = await _get_marketplace_tenant_or_404(slug)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketplace item not found.")
    return serialize_document(item)


async def _resolve_item_for_customer(tenant_oid: ObjectId, item_id: str) -> dict:
    db = get_database()
    item_oid = parse_object_id(item_id, "itemId")
    item = await db.items.find_one(
        {
            "_id": item_oid,
            "tenantId": tenant_oid,
            "status": "active",
            "$or": [{"isSellable": True}, {"isBookable": True}],
        }
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketplace item not found.")
    return item


async def get_customer_cart(current_user: dict) -> list[dict]:
    db = get_database()
    _, user_id = await _get_customer_profile_and_user(current_user)
    cursor = db.carts.find({"customerUserId": ObjectId(user_id), "status": "active"}).sort("updatedAt", -1)
    carts = []
    async for cart in cursor:
        tenant = await db.tenants.find_one({"_id": cart["tenantId"]})
        item_ids = [item["itemId"] for item in cart.get("items", [])]
        item_map = {
            item["_id"]: item
            async for item in db.items.find({"_id": {"$in": item_ids}})
        } if item_ids else {}
        serialized = serialize_document(cart)
        serialized["tenant"] = serialize_document(tenant) if tenant else None
        transaction_custom_fields = await _list_custom_fields_for_tenant_oid(cart["tenantId"], "transactions", "transaction")
        category_hints = ((tenant or {}).get("settings") or {}).get("categoryHints") or {}
        fulfillment_rules = category_hints.get("fulfillment") or {}
        payment_options = await get_customer_payment_options_for_tenant(cart["tenantId"])
        serialized["checkoutConfig"] = {
            "allowedFulfillmentTypes": fulfillment_rules.get("allowedTypes", ["none"]),
            "defaultFulfillmentType": fulfillment_rules.get("defaultType", "none"),
            "transactionCustomFields": [field for field in transaction_custom_fields if field.get("isActive")],
            "paymentOptions": payment_options,
        }
        items_detailed = []
        for item in cart.get("items", []):
            item_data = serialize_document(item_map[item["itemId"]]) if item_map.get(item["itemId"]) else {"id": str(item["itemId"]), "name": "Unavailable"}
            item_data["quantity"] = item["quantity"]
            items_detailed.append(item_data)
        serialized["itemsDetailed"] = items_detailed
        carts.append(serialized)
    return carts


async def list_customer_favorites(current_user: dict) -> list[dict]:
    db = get_database()
    _, user_id = await _get_customer_profile_and_user(current_user)
    cursor = db.customer_favorites.find({"customerUserId": ObjectId(user_id)}).sort("createdAt", -1)
    favorites = []
    async for favorite in cursor:
        tenant = await db.tenants.find_one({"_id": favorite["tenantId"]})
        item = await db.items.find_one({"_id": favorite["itemId"]})
        if not tenant or not item:
            continue
        serialized = serialize_document(favorite)
        serialized["tenant"] = serialize_document(tenant)
        serialized["item"] = serialize_document(item)
        favorites.append(serialized)
    return favorites


async def add_customer_favorite(payload, current_user: dict) -> list[dict]:
    db = get_database()
    profile, user_id = await _get_customer_profile_and_user(current_user)
    tenant_oid = parse_object_id(payload.tenantId, "tenantId")
    item = await _resolve_item_for_customer(tenant_oid, payload.itemId)
    tenant = await db.tenants.find_one({"_id": tenant_oid})
    if tenant:
        await ensure_customer_record_for_tenant(
            tenant,
            customer_user_id=current_user["_id"],
            customer_profile_id=profile["_id"],
            name=current_user.get("fullName", ""),
            phone=normalize_optional_pk_phone_or_blank(profile.get("phone") or current_user.get("phone", "")),
            email=current_user.get("email", ""),
            address=profile.get("defaultAddress") or {},
            source_tag="customer_portal",
        )
    now = datetime.now(timezone.utc)
    await db.customer_favorites.update_one(
        {"customerUserId": ObjectId(user_id), "tenantId": tenant_oid, "itemId": item["_id"]},
        {
            "$setOnInsert": {
                "customerUserId": ObjectId(user_id),
                "tenantId": tenant_oid,
                "itemId": item["_id"],
                "createdAt": now,
                "updatedAt": now,
            }
        },
        upsert=True,
    )
    return await list_customer_favorites(current_user)


async def remove_customer_favorite(item_id: str, tenant_id: str, current_user: dict) -> list[dict]:
    db = get_database()
    _, user_id = await _get_customer_profile_and_user(current_user)
    item_oid = parse_object_id(item_id, "itemId")
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await db.customer_favorites.delete_one({"customerUserId": ObjectId(user_id), "tenantId": tenant_oid, "itemId": item_oid})
    return await list_customer_favorites(current_user)


async def add_cart_item(payload, current_user: dict) -> list[dict]:
    db = get_database()
    profile, user_id = await _get_customer_profile_and_user(current_user)
    tenant_oid = parse_object_id(payload.tenantId, "tenantId")
    tenant = await db.tenants.find_one(
        {
            "_id": tenant_oid,
            "status": "active",
            "websiteStatus": "published",
            "enabledModuleCodes": "customer_portal",
        }
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketplace business not found.")

    await ensure_customer_record_for_tenant(
        tenant,
        customer_user_id=current_user["_id"],
        customer_profile_id=profile["_id"],
        name=current_user.get("fullName", ""),
        phone=normalize_optional_pk_phone_or_blank(profile.get("phone") or current_user.get("phone", "")),
        email=current_user.get("email", ""),
        address=profile.get("defaultAddress") or {},
        source_tag="customer_portal",
    )
    item = await _resolve_item_for_customer(tenant_oid, payload.itemId)
    now = datetime.now(timezone.utc)
    cart = await db.carts.find_one({"customerUserId": ObjectId(user_id), "tenantId": tenant_oid, "status": "active"})
    if not cart:
        cart = {
            "customerUserId": ObjectId(user_id),
            "tenantId": tenant_oid,
            "items": [{"itemId": item["_id"], "quantity": payload.quantity}],
            "status": "active",
            "createdAt": now,
            "updatedAt": now,
        }
        await db.carts.insert_one(cart)
    else:
        existing = next((cart_item for cart_item in cart["items"] if cart_item["itemId"] == item["_id"]), None)
        if existing:
            existing["quantity"] = min(existing["quantity"] + payload.quantity, 99)
            await db.carts.update_one(
                {"_id": cart["_id"]},
                {"$set": {"items": cart["items"], "updatedAt": now}},
            )
        else:
            await db.carts.update_one(
                {"_id": cart["_id"]},
                {"$push": {"items": {"itemId": item["_id"], "quantity": payload.quantity}}, "$set": {"updatedAt": now}},
            )
    return await get_customer_cart(current_user)


async def update_cart_item(item_id: str, payload, current_user: dict) -> list[dict]:
    db = get_database()
    _, user_id = await _get_customer_profile_and_user(current_user)
    item_oid = parse_object_id(item_id, "itemId")
    carts = await db.carts.find({"customerUserId": ObjectId(user_id), "status": "active"}).to_list(length=None)
    matched = False
    for cart in carts:
        changed = False
        for cart_item in cart.get("items", []):
            if cart_item["itemId"] == item_oid:
                cart_item["quantity"] = max(1, min(int(payload.quantity), 99))
                changed = True
                matched = True
                break
        if changed:
            await db.carts.update_one({"_id": cart["_id"]}, {"$set": {"items": cart["items"], "updatedAt": datetime.now(timezone.utc)}})
    if not matched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found.")
    return await get_customer_cart(current_user)


async def remove_cart_item(item_id: str, current_user: dict) -> list[dict]:
    db = get_database()
    _, user_id = await _get_customer_profile_and_user(current_user)
    item_oid = parse_object_id(item_id, "itemId")
    result = await db.carts.update_many(
        {"customerUserId": ObjectId(user_id), "status": "active"},
        {"$pull": {"items": {"itemId": item_oid}}, "$set": {"updatedAt": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found.")
    await db.carts.update_many(
        {"customerUserId": ObjectId(user_id), "status": "active", "items": []},
        {"$set": {"status": "abandoned", "updatedAt": datetime.now(timezone.utc)}},
    )
    return await get_customer_cart(current_user)


async def _build_transaction_from_items(
    tenant: dict,
    items: list[dict],
    fulfillment: dict,
    notes: str,
    custom_fields: dict,
    current_user: dict,
    profile: dict,
    source: str,
    requested_transaction_type: str | None = None,
    payment_method: str | None = None,
) -> dict:
    db = get_database()
    normalized_fulfillment = normalize_fulfillment(fulfillment)
    validate_tenant_fulfillment(tenant, normalized_fulfillment)
    normalized_notes = normalize_notes(notes)
    normalized_custom_fields = await validate_custom_values_for_tenant_oid(tenant["_id"], "transactions", "transaction", custom_fields or {})
    if not normalized_custom_fields["valid"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=normalized_custom_fields["errors"])
    resolved_items, order_items, subtotal = await resolve_requested_order_items(tenant, items, db)

    now = datetime.now(timezone.utc)
    transaction_type = infer_transaction_type(normalize_transaction_type(requested_transaction_type), resolved_items)
    customer_phone = normalize_optional_pk_phone_or_blank(profile.get("phone") or current_user.get("phone", ""))
    payment_options = await get_customer_payment_options_for_tenant(tenant["_id"])
    payment_preference = normalize_customer_payment_preference(payment_method, payment_options)
    transaction = {
        "tenantId": tenant["_id"],
        "branchId": None,
        "customerId": None,
        "customerUserId": current_user["_id"],
        "customerProfileId": profile["_id"],
        "transactionType": transaction_type,
        "transactionNumber": await generate_transaction_number(tenant["_id"], transaction_type),
        "source": source,
        "status": get_initial_transaction_status(transaction_type),
        "items": order_items,
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
            "name": current_user.get("fullName", ""),
            "phone": customer_phone,
            "email": current_user.get("email", ""),
        },
        "notes": normalized_notes,
        "internalNotes": "",
        "customFields": normalized_custom_fields["values"],
        "statusHistory": [
            {
                "field": "status",
                "from": None,
                "to": get_initial_transaction_status(transaction_type),
                "note": f"Created from {source}.",
                "changedAt": now,
                "changedByUserId": current_user["_id"],
            }
        ],
        "createdBy": current_user["_id"],
        "createdAt": now,
        "updatedAt": now,
    }
    transaction["_id"] = (await db.transactions.insert_one(transaction)).inserted_id
    try:
        transaction = await reserve_transaction_stock(transaction, current_user.get("_id"))
    except Exception:
        await db.transactions.delete_one({"_id": transaction["_id"]})
        raise
    customer_id = await sync_customer_stats_for_transaction(tenant, transaction)
    transaction["customerId"] = customer_id
    await create_business_notification(
        tenant["_id"],
        "order_alert",
        f"New {transaction_type.replace('_', ' ')} {transaction['transactionNumber']}",
        f"{transaction.get('customerSnapshot', {}).get('name') or 'A customer'} created a new {transaction_type.replace('_', ' ')} from {source}.",
        priority="high" if transaction_type == "order" else "medium",
        metadata={
            "transactionId": str(transaction["_id"]),
            "transactionNumber": transaction["transactionNumber"],
            "transactionType": transaction_type,
            "source": source,
            "customerName": transaction.get("customerSnapshot", {}).get("name", ""),
            "tenantSlug": tenant.get("slug", ""),
        },
    )
    await create_customer_notification(
        current_user["_id"],
        tenant["_id"],
        "transaction_created",
        f"{transaction['transactionNumber']} created",
        f"Your {transaction_type.replace('_', ' ')} was created successfully for {tenant.get('name', 'this business')}.",
        {"transactionId": str(transaction["_id"]), "transactionType": transaction_type, "tenantSlug": tenant.get("slug", "")},
    )
    return transaction


async def create_customer_transaction(payload, current_user: dict) -> dict:
    db = get_database()
    profile, user_id = await _get_customer_profile_and_user(current_user)
    tenant_oid = parse_object_id(payload.tenantId, "tenantId")
    tenant = await db.tenants.find_one(
        {
            "_id": tenant_oid,
            "status": "active",
            "websiteStatus": "published",
            "enabledModuleCodes": "customer_portal",
        }
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketplace business not found.")

    cart = await db.carts.find_one({"customerUserId": ObjectId(user_id), "tenantId": tenant_oid, "status": "active"})
    if not cart or not cart.get("items"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cart is empty.")

    transaction = await _build_transaction_from_items(
        tenant,
        [
            {
                "itemId": str(item["itemId"]),
                "quantity": item["quantity"],
                "selectedVariantIndex": item.get("selectedVariantIndex"),
                "selectedVariantName": item.get("selectedVariantName", ""),
                "selectedOptions": item.get("selectedOptions") or {},
                "variantSku": item.get("variantSku", ""),
            }
            for item in cart["items"]
        ],
        payload.fulfillment,
        payload.notes,
        payload.customFields,
        current_user,
        profile,
        "customer_portal",
        getattr(payload, "transactionType", None),
        getattr(payload, "paymentMethod", None),
    )
    await db.carts.update_one({"_id": cart["_id"]}, {"$set": {"status": "checked_out", "updatedAt": datetime.now(timezone.utc)}})
    return serialize_document(transaction)


async def confirm_customer_draft_order(slug: str, payload, current_user: dict) -> dict:
    profile, _ = await _get_customer_profile_and_user(current_user)
    tenant = await _get_marketplace_tenant_or_404(slug)
    transaction = await _build_transaction_from_items(
        tenant,
        payload.items,
        payload.fulfillment,
        payload.notes,
        payload.customFields,
        current_user,
        profile,
        "customer_portal",
        getattr(payload, "transactionType", None),
        getattr(payload, "paymentMethod", None),
    )
    await clear_customer_conversation_draft(slug, payload.conversationId, current_user, transaction)
    return serialize_document(transaction)


async def list_customer_transactions(current_user: dict, page: int = 1, limit: int = 20) -> dict:
    db = get_database()
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    total = await db.transactions.count_documents({"customerUserId": current_user["_id"]})
    cursor = (
        db.transactions.find({"customerUserId": current_user["_id"]})
        .sort("createdAt", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    items = []
    async for order in cursor:
        serialized = serialize_document(order)
        serialized["paymentProofSummary"] = await summarize_payment_records_for_transaction(order)
        items.append(serialized)
    return {
        "items": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit,
        },
    }


async def get_customer_transaction(order_id: str, current_user: dict) -> dict:
    db = get_database()
    order_oid = parse_object_id(order_id, "orderId")
    order = await db.transactions.find_one({"_id": order_oid, "customerUserId": current_user["_id"]})
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    serialized = serialize_document(order)
    serialized["paymentInstructions"] = order.get("paymentInstructions") or await get_customer_payment_options_for_tenant(order["tenantId"])
    serialized["paymentRecords"] = await list_customer_payment_records_for_transaction(order)
    serialized["paymentProofSummary"] = await summarize_payment_records_for_transaction(order)
    return serialized


async def reorder_customer_transaction(order_id: str, current_user: dict) -> dict:
    db = get_database()
    _, user_id = await _get_customer_profile_and_user(current_user)
    order_oid = parse_object_id(order_id, "orderId")
    transaction = await db.transactions.find_one({"_id": order_oid, "customerUserId": current_user["_id"]})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    tenant = await db.tenants.find_one(
        {
            "_id": transaction["tenantId"],
            "status": "active",
            "websiteStatus": "published",
            "enabledModuleCodes": "customer_portal",
        }
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketplace business not found.")
    now = datetime.now(timezone.utc)
    cart = await db.carts.find_one({"customerUserId": ObjectId(user_id), "tenantId": tenant["_id"], "status": "active"})
    if not cart:
        cart = {
            "customerUserId": ObjectId(user_id),
            "tenantId": tenant["_id"],
            "items": [],
            "status": "active",
            "createdAt": now,
            "updatedAt": now,
        }
        cart["_id"] = (await db.carts.insert_one(cart)).inserted_id

    current_items = {item["itemId"]: item for item in cart.get("items", [])}
    for item in transaction.get("items", []):
        item_oid = item["itemId"]
        live_item = await db.items.find_one(
            {
                "_id": item_oid,
                "tenantId": tenant["_id"],
                "status": "active",
                "$or": [{"isSellable": True}, {"isBookable": True}],
            }
        )
        if not live_item:
            continue
        if item_oid in current_items:
            current_items[item_oid]["quantity"] = min(current_items[item_oid]["quantity"] + int(item.get("quantity", 1)), 99)
        else:
            current_items[item_oid] = {"itemId": item_oid, "quantity": min(int(item.get("quantity", 1)), 99)}
    await db.carts.update_one(
        {"_id": cart["_id"]},
        {"$set": {"items": list(current_items.values()), "updatedAt": now}},
    )
    await create_customer_notification(
        current_user["_id"],
        tenant["_id"],
        "reorder_ready",
        f"Reorder prepared for {tenant.get('name', 'business')}",
        f"Items from {transaction.get('transactionNumber', 'your transaction')} were added back to your cart.",
        {"transactionId": str(transaction["_id"]), "tenantSlug": tenant.get("slug", "")},
    )
    return {
        "transactionId": str(transaction["_id"]),
        "tenantSlug": tenant.get("slug", ""),
        "itemsAdded": len(list(current_items.values())),
    }


async def create_customer_order(payload, current_user: dict) -> dict:
    return await create_customer_transaction(payload, current_user)


async def list_customer_orders(current_user: dict, page: int = 1, limit: int = 20) -> dict:
    return await list_customer_transactions(current_user, page, limit)


async def get_customer_order(order_id: str, current_user: dict) -> dict:
    return await get_customer_transaction(order_id, current_user)
