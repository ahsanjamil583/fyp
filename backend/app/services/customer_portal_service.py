import logging
from datetime import datetime, timezone
import re

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.item_views import customer_item_view
from app.core.public_views import public_business_view, customer_order_view
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
from app.services.order_message_service import notify_order_placed
from app.services.order_validation_service import normalize_fulfillment, normalize_notes
from app.services.payment_service import get_customer_payment_options_for_tenant, normalize_customer_payment_preference
from app.services.payment_service import list_customer_payment_records_for_transaction, summarize_payment_records_for_transaction
from app.services.smart_order_service import claim_order_submission, MAX_LINE_QUANTITY, resolve_requested_order_items
from app.services.transaction_number_service import generate_transaction_number
from app.services.transaction_workflow_service import (
    get_initial_payment_status,
    get_initial_transaction_status,
    infer_transaction_type,
    normalize_transaction_type,
)
from app.services.whatsapp_service import get_customer_facing_whatsapp_agent

logger = logging.getLogger(__name__)


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
        query["address.city"] = {"$regex": re.escape(city[:200]), "$options": "i"}
    if category_id:
        query["businessCategoryId"] = parse_object_id(category_id, "businessCategoryId")
    if search:
        search = re.escape(search[:200])
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"address.city": {"$regex": search, "$options": "i"}},
        ]

    total = await db.tenants.count_documents(query)
    cursor = db.tenants.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    items = []
    async for tenant in cursor:
        serialized = public_business_view(tenant)
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


# --- Cross-business catalog -------------------------------------------------
# Customers should be able to shop by product without picking a business first.
# The per-business endpoints stay as they are; this aggregates over exactly the
# same "published and publicly visible" tenant set.

MARKETPLACE_TENANT_QUERY = {
    "status": "active",
    "websiteStatus": "published",
    "settings.publicVisibility": True,
    "enabledModuleCodes": "customer_portal",
}


def _storefront_summary(tenant: dict) -> dict:
    """The small, safe slice of a business shown on a product card."""
    address = tenant.get("address") or {}
    return {
        # id is needed for cart/order payloads; it is never rendered in the UI.
        "id": str(tenant.get("_id")),
        "name": tenant.get("name", ""),
        "slug": tenant.get("slug", ""),
        "city": address.get("city", ""),
        "province": address.get("province", ""),
        "websiteStatus": tenant.get("websiteStatus", ""),
        "hasPublishedWebsite": tenant.get("websiteStatus") == "published",
    }


async def list_marketplace_catalog(
    search: str = "",
    item_type: str | None = None,
    city: str = "",
    business_category_id: str | None = None,
    category: str = "",
    page: int = 1,
    limit: int = 24,
) -> dict:
    db = get_database()
    page = max(page, 1)
    limit = min(max(limit, 1), 60)

    tenant_query = dict(MARKETPLACE_TENANT_QUERY)
    if city:
        tenant_query["address.city"] = {"$regex": re.escape(city[:200]), "$options": "i"}
    if business_category_id:
        tenant_query["businessCategoryId"] = parse_object_id(business_category_id, "businessCategoryId")

    # Only the fields the storefront summary and the facets actually read, rather than
    # every field of every published tenant.
    tenants = await db.tenants.find(
        tenant_query,
        # _storefront_summary reads name, slug, address and websiteStatus; the facets
        # read address.city. Dropping websiteStatus here would silently make every
        # storefront card report that it has no published website.
        {"name": 1, "slug": 1, "address": 1, "websiteStatus": 1, "settings": 1, "businessCategoryId": 1},
    ).to_list(length=None)
    tenant_map = {tenant["_id"]: tenant for tenant in tenants}
    if not tenant_map:
        return {
            "items": [],
            "facets": {"categories": [], "itemTypes": [], "cities": []},
            "pagination": {"page": page, "limit": limit, "total": 0, "totalPages": 0},
        }

    tenant_ids = list(tenant_map.keys())
    base_query: dict = {
        "tenantId": {"$in": tenant_ids},
        "status": "active",
        "$or": [{"isSellable": True}, {"isBookable": True}],
    }

    query = dict(base_query)
    if item_type:
        query["itemType"] = item_type
    if category:
        # Category names are per-tenant, so the filter matches on the name across
        # businesses. Asking the database for that one name is what this needs; loading
        # every category of every published tenant to find it was the expensive way.
        wanted = category.strip()
        matching_ids = [
            doc["_id"]
            async for doc in db.item_categories.find(
                {
                    "tenantId": {"$in": tenant_ids},
                    "isActive": {"$ne": False},
                    "name": {"$regex": f"^{re.escape(wanted[:200])}$", "$options": "i"},
                },
                {"_id": 1},
            )
        ]
        query["categoryId"] = {"$in": matching_ids} if matching_ids else {"$in": []}
    if search:
        safe = re.escape(search[:200])
        matching_tenant_ids = [
            tid for tid, tenant in tenant_map.items()
            if re.search(safe, str(tenant.get("name") or ""), re.IGNORECASE)
        ]
        query["$and"] = [
            {"$or": query.pop("$or")},
            {
                "$or": [
                    {"name": {"$regex": safe, "$options": "i"}},
                    {"description": {"$regex": safe, "$options": "i"}},
                    {"tags": {"$regex": safe, "$options": "i"}},
                    {"tenantId": {"$in": matching_tenant_ids}},
                ]
            },
        ]

    total = await db.items.count_documents(query)
    cursor = db.items.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)

    page_items = [item async for item in cursor]

    # Facets come from the unfiltered published set so options never disappear as the
    # customer narrows the results. This used to load every item of every published
    # tenant into memory on every page view; grouping in the database returns one row
    # per distinct value instead.
    facet_rows = await db.items.aggregate(
        [
            {"$match": base_query},
            {"$group": {"_id": {"categoryId": "$categoryId", "itemType": "$itemType"}}},
        ]
    ).to_list(length=None)
    # Resolve names for exactly the categories in play - the ones on this page, plus the
    # distinct ones the facet turned up - rather than every category on the platform.
    needed_category_ids = {item.get("categoryId") for item in page_items if item.get("categoryId")}
    needed_category_ids.update(row["_id"].get("categoryId") for row in facet_rows if row["_id"].get("categoryId"))
    category_names = {
        doc["_id"]: (doc.get("name") or "").strip()
        async for doc in db.item_categories.find(
            {"_id": {"$in": list(needed_category_ids)}, "isActive": {"$ne": False}},
            {"name": 1},
        )
    } if needed_category_ids else {}

    items = []
    for item in page_items:
        view = customer_item_view(item)
        tenant = tenant_map.get(item.get("tenantId")) or {}
        view["business"] = _storefront_summary(tenant)
        view["categoryName"] = category_names.get(item.get("categoryId"), "")
        items.append(view)

    facet_categories = sorted({
        name for name in (category_names.get(row["_id"].get("categoryId"), "") for row in facet_rows) if name
    })
    facet_types = sorted({row["_id"].get("itemType") for row in facet_rows if row["_id"].get("itemType")})
    facet_cities = sorted({
        (tenant.get("address") or {}).get("city", "") for tenant in tenant_map.values()
        if (tenant.get("address") or {}).get("city")
    })

    return {
        "items": items,
        "facets": {"categories": facet_categories, "itemTypes": facet_types, "cities": facet_cities},
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit,
        },
    }


async def get_marketplace_business(slug: str) -> dict:
    tenant = await _get_marketplace_tenant_or_404(slug)
    serialized = public_business_view(tenant)
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
    return customer_item_view(item)


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


# Cart line helpers live in app.core.cart_lines so the agent's basket can use them
# without importing this service. Re-exported here because callers already import
# them from this module.
from app.core.cart_lines import (  # noqa: F401
    build_cart_line,
    cart_line_key,
    cart_line_unit_price,
    find_cart_line,
)


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
        serialized["tenant"] = public_business_view(tenant) if tenant else None
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
        for line in cart.get("items", []):
            source_item = item_map.get(line["itemId"])
            # customer_item_view, not serialize_document: the raw document carries
            # costPrice and exact on-hand quantities, and this endpoint is the one place
            # in the customer portal that was handing them to the customer.
            item_data = customer_item_view(source_item) if source_item else {"id": str(line["itemId"]), "name": "Unavailable"}
            item_data["quantity"] = line.get("quantity", 1)
            item_data["lineId"] = line.get("lineId", str(line["itemId"]))
            item_data["selectedVariantIndex"] = line.get("selectedVariantIndex")
            item_data["selectedVariantName"] = line.get("selectedVariantName", "")
            item_data["selectedOptions"] = line.get("selectedOptions") or {}
            item_data["variantSku"] = line.get("variantSku", "")
            item_data["unitPrice"] = cart_line_unit_price(source_item, line)
            items_detailed.append(item_data)
        serialized["itemsDetailed"] = items_detailed
        carts.append(serialized)
    return carts


async def list_customer_favorites(current_user: dict) -> list[dict]:
    db = get_database()
    _, user_id = await _get_customer_profile_and_user(current_user)
    rows = await db.customer_favorites.find({"customerUserId": ObjectId(user_id)}).sort("createdAt", -1).to_list(length=500)
    if not rows:
        return []

    # One query per collection instead of two per favourite.
    tenant_map = {
        tenant["_id"]: tenant
        async for tenant in db.tenants.find({"_id": {"$in": list({row["tenantId"] for row in rows})}})
    }
    item_map = {
        item["_id"]: item
        async for item in db.items.find({"_id": {"$in": list({row["itemId"] for row in rows})}})
    }

    favorites = []
    for favorite in rows:
        tenant = tenant_map.get(favorite["tenantId"])
        item = item_map.get(favorite["itemId"])
        if not tenant or not item:
            continue
        serialized = serialize_document(favorite)
        serialized["tenant"] = public_business_view(tenant)
        serialized["item"] = customer_item_view(item)
        favorites.append(serialized)
    return favorites


async def add_customer_favorite(payload, current_user: dict) -> list[dict]:
    db = get_database()
    profile, user_id = await _get_customer_profile_and_user(current_user)
    tenant_oid = parse_object_id(payload.tenantId, "tenantId")
    item = await _resolve_item_for_customer(tenant_oid, payload.itemId)
    # Favouriting is a write path like cart, checkout and reorder, and it creates a
    # customer record on the business. It had no tenant guard at all, so a hidden,
    # unpublished or inactive business still accepted favourites by id from a stranger.
    tenant = await db.tenants.find_one(
        {
            "_id": tenant_oid,
            "status": "active",
            "websiteStatus": "published",
            "settings.publicVisibility": True,
            "enabledModuleCodes": "customer_portal",
        }
    )
    # Same shape as cart, checkout and reorder: refuse outright rather than carrying on
    # with the favourite while quietly skipping the customer record. A hidden business
    # should not gain favourites either.
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
            # A business that has hidden itself must not keep taking orders by id.
            # Every read path already applies this; the write paths did not.
            "settings.publicVisibility": True,
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
    line = build_cart_line(item, payload)
    cart = await db.carts.find_one({"customerUserId": ObjectId(user_id), "tenantId": tenant_oid, "status": "active"})
    if not cart:
        cart = {
            "customerUserId": ObjectId(user_id),
            "tenantId": tenant_oid,
            "items": [line],
            "status": "active",
            "createdAt": now,
            "updatedAt": now,
        }
        await db.carts.insert_one(cart)
    else:
        # Two different variants of one item are two lines. Merging on itemId alone put
        # "Blue / Large" and "Red / Small" into the same row and lost one of them.
        existing = next(
            (cart_item for cart_item in cart["items"] if cart_line_key(cart_item) == cart_line_key(line)),
            None,
        )
        if existing:
            existing["quantity"] = min(int(existing.get("quantity", 0)) + payload.quantity, MAX_LINE_QUANTITY)
            existing.setdefault("lineId", line["lineId"])
            await db.carts.update_one(
                {"_id": cart["_id"]},
                {"$set": {"items": cart["items"], "updatedAt": now}},
            )
        else:
            await db.carts.update_one(
                {"_id": cart["_id"]},
                {"$push": {"items": line}, "$set": {"updatedAt": now}},
            )
    return await get_customer_cart(current_user)


async def update_cart_item(line_reference: str, payload, current_user: dict) -> list[dict]:
    """Change the quantity of one cart line.

    ``line_reference`` is a lineId. Carts created before lines had ids are still
    addressable by itemId, which is why the match is not strict.
    """
    db = get_database()
    _, user_id = await _get_customer_profile_and_user(current_user)
    carts = await db.carts.find({"customerUserId": ObjectId(user_id), "status": "active"}).to_list(length=None)
    matched = False
    for cart in carts:
        target = find_cart_line(cart, line_reference)
        if not target:
            continue
        target["quantity"] = max(1, min(int(payload.quantity), MAX_LINE_QUANTITY))
        matched = True
        await db.carts.update_one(
            {"_id": cart["_id"]},
            {"$set": {"items": cart["items"], "updatedAt": datetime.now(timezone.utc)}},
        )
        break
    if not matched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found.")
    return await get_customer_cart(current_user)


async def remove_cart_item(line_reference: str, current_user: dict) -> list[dict]:
    """Remove one cart line.

    Previously this pulled every line sharing an itemId, so removing one variant took
    the others with it.
    """
    db = get_database()
    _, user_id = await _get_customer_profile_and_user(current_user)
    carts = await db.carts.find({"customerUserId": ObjectId(user_id), "status": "active"}).to_list(length=None)
    matched = False
    for cart in carts:
        target = find_cart_line(cart, line_reference)
        if not target:
            continue
        remaining = [line for line in cart.get("items", []) if line is not target]
        matched = True
        await db.carts.update_one(
            {"_id": cart["_id"]},
            {"$set": {"items": remaining, "updatedAt": datetime.now(timezone.utc)}},
        )
        break
    if not matched:
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
    # Everything past this point is a side effect. The order exists and its stock is
    # reserved, so a failure here must not propagate: the caller restores the cart to
    # "active" on any exception, which would hand the customer a live cart for an order
    # that had already been placed, and a retry would then place it twice.
    try:
        transaction["customerId"] = await sync_customer_stats_for_transaction(tenant, transaction)
    except Exception:
        logger.exception("Customer stats sync failed for %s.", transaction.get("transactionNumber"))
    try:
        await _announce_new_transaction(tenant, transaction, transaction_type, source, current_user)
    except Exception:
        logger.exception("Order notifications failed for %s.", transaction.get("transactionNumber"))
    return transaction


async def _announce_new_transaction(tenant: dict, transaction: dict, transaction_type: str, source: str, current_user: dict) -> None:
    """Owner alert, customer confirmation and the order-placed message. Best effort."""
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
    # Best-effort: a confirmation that cannot be sent must never undo the order.
    await notify_order_placed(transaction, tenant)
    await create_customer_notification(
        current_user["_id"],
        tenant["_id"],
        "transaction_created",
        f"{transaction['transactionNumber']} created",
        f"Your {transaction_type.replace('_', ' ')} was created successfully for {tenant.get('name', 'this business')}.",
        {"transactionId": str(transaction["_id"]), "transactionType": transaction_type, "tenantSlug": tenant.get("slug", "")},
    )


async def create_customer_transaction(payload, current_user: dict) -> dict:
    db = get_database()
    profile, user_id = await _get_customer_profile_and_user(current_user)
    tenant_oid = parse_object_id(payload.tenantId, "tenantId")
    tenant = await db.tenants.find_one(
        {
            "_id": tenant_oid,
            "status": "active",
            "websiteStatus": "published",
            # A business that has hidden itself must not keep taking orders by id.
            # Every read path already applies this; the write paths did not.
            "settings.publicVisibility": True,
            "enabledModuleCodes": "customer_portal",
        }
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketplace business not found.")

    # Claim the cart before building anything. Reading it, creating the order and only
    # then flipping the status left a window in which a double-click or a client retry
    # created two orders and reserved the stock twice.
    # The claim uses the final status rather than a new intermediate one, so no other
    # query has to learn about a state it has never seen. On any failure below the cart
    # is handed straight back to the customer.
    cart = await db.carts.find_one_and_update(
        {"customerUserId": ObjectId(user_id), "tenantId": tenant_oid, "status": "active"},
        {"$set": {"status": "checked_out", "updatedAt": datetime.now(timezone.utc)}},
    )
    if not cart or not cart.get("items"):
        if cart:
            await db.carts.update_one({"_id": cart["_id"]}, {"$set": {"status": "active"}})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cart is empty.")

    try:
        transaction = await _build_transaction_from_items(
            tenant,
            [
                {
                    "itemId": str(item["itemId"]),
                    "lineId": item.get("lineId", ""),
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
    except Exception:
        # The order was not created, so the customer gets their cart back rather than
        # losing it to a failed attempt.
        await db.carts.update_one({"_id": cart["_id"]}, {"$set": {"status": "active", "updatedAt": datetime.now(timezone.utc)}})
        raise
    return customer_order_view(transaction)


async def _claim_conversation_draft(slug: str, conversation_id, current_user: dict) -> None:
    """Take the pending draft off the conversation before acting on it.

    Whoever clears it is the one allowed to place the order. A second request finds it
    already gone and is refused, which is what stops a double submit from creating two
    orders and reserving the stock twice.
    """
    if not conversation_id:
        return
    db = get_database()
    tenant = await db.tenants.find_one({"slug": slug}, {"_id": 1})
    if not tenant:
        return
    claimed = await db.conversations.find_one_and_update(
        {
            "_id": parse_object_id(str(conversation_id), "conversationId"),
            "tenantId": tenant["_id"],
            "customerUserId": current_user["_id"],
            "pendingOrderDraft": {"$nin": [None, {}]},
        },
        {"$set": {"pendingOrderDraft": {}, "updatedAt": datetime.now(timezone.utc)}},
    )
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That draft order has already been placed. Open your orders to see it.",
        )


async def confirm_customer_draft_order(slug: str, payload, current_user: dict) -> dict:
    db = get_database()
    profile, _ = await _get_customer_profile_and_user(current_user)
    tenant = await _get_marketplace_tenant_or_404(slug)
    # Unlike checkout there is no cart to claim here, so a double-click or a client retry
    # created two orders and reserved the stock twice. The conversation's draft is the
    # thing being confirmed, so claiming that is the equivalent guard.
    await _claim_conversation_draft(slug, getattr(payload, "conversationId", None), current_user)
    # conversationId is optional, and the claim above returns early without it, so the
    # submission is claimed as well. Otherwise omitting one field defeated the guard.
    await claim_order_submission(
        db,
        tenant["_id"],
        [
            str(current_user["_id"]),
            *(f"{getattr(entry, 'itemId', '')}x{getattr(entry, 'quantity', 1)}" for entry in (payload.items or [])),
        ],
    )
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
    return customer_order_view(transaction)


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
        serialized = customer_order_view(order)
        serialized["paymentProofSummary"] = await summarize_payment_records_for_transaction(order, for_customer=True)
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
    serialized = customer_order_view(order)
    serialized["paymentInstructions"] = order.get("paymentInstructions") or await get_customer_payment_options_for_tenant(order["tenantId"])
    serialized["paymentRecords"] = await list_customer_payment_records_for_transaction(order)
    serialized["paymentProofSummary"] = await summarize_payment_records_for_transaction(order, for_customer=True)
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
            # A business that has hidden itself must not keep taking orders by id.
            # Every read path already applies this; the write paths did not.
            "settings.publicVisibility": True,
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

    # Lines are keyed by item AND variant, exactly as add_cart_item does. Keying by
    # itemId alone collapsed two variants of one item into a single row and dropped one,
    # and the rebuilt line carried no variant at all, so checkout silently fell back to
    # the default variant.
    lines = list(cart.get("items", []))
    lines_added = 0
    for ordered in transaction.get("items", []):
        item_oid = ordered["itemId"]
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
        quantity = min(max(int(ordered.get("quantity", 1) or 1), 1), MAX_LINE_QUANTITY)
        line = build_cart_line(live_item, _ReorderLineRequest(ordered, quantity))
        existing = next((line_item for line_item in lines if cart_line_key(line_item) == cart_line_key(line)), None)
        if existing:
            existing["quantity"] = min(int(existing.get("quantity", 0)) + quantity, MAX_LINE_QUANTITY)
            existing.setdefault("lineId", line["lineId"])
        else:
            lines.append(line)
        lines_added += 1
    await db.carts.update_one(
        {"_id": cart["_id"]},
        {"$set": {"items": lines, "updatedAt": now}},
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
        # Lines actually reordered, not the size of the whole cart.
        "itemsAdded": lines_added,
    }


class _ReorderLineRequest:
    """Adapts a stored transaction line to the add-to-cart request shape.

    `build_cart_line` resolves the variant through the same helper the order builder
    uses, so a variant that no longer exists is refused here rather than silently
    swapped for the default at checkout.
    """

    def __init__(self, ordered: dict, quantity: int) -> None:
        self.itemId = str(ordered.get("itemId", ""))
        self.quantity = quantity
        self.selectedVariantIndex = ordered.get("selectedVariantIndex")
        self.selectedVariantName = ordered.get("selectedVariantName", "")
        self.variantSku = ordered.get("variantSku", "")
        self.selectedOptions = ordered.get("selectedOptions") or {}


async def create_customer_order(payload, current_user: dict) -> dict:
    return await create_customer_transaction(payload, current_user)


async def list_customer_orders(current_user: dict, page: int = 1, limit: int = 20) -> dict:
    return await list_customer_transactions(current_user, page, limit)


async def get_customer_order(order_id: str, current_user: dict) -> dict:
    return await get_customer_transaction(order_id, current_user)
