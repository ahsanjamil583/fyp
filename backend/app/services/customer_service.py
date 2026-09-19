import logging
from datetime import datetime, timedelta, timezone
import re

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.module_guard import ensure_tenant_module_enabled, ensure_tenant_module_usage_available
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.localization_service import normalize_optional_email, normalize_optional_pk_phone, normalize_optional_pk_phone_or_blank
from app.services.custom_field_service import validate_custom_values
from app.services.transaction_workflow_service import is_revenue_transaction

logger = logging.getLogger(__name__)

ALLOWED_CUSTOMER_STATUSES = {"active", "inactive", "blocked"}
ALLOWED_CUSTOMER_TYPES = {"customer", "client", "patient", "student", "member", "lead"}
DEFAULT_SEGMENTS = {"all", "new", "repeat", "high_value", "inactive", "vip", "customer_portal", "website"}

# Segment membership is computed per document, so a segment filter cannot be pushed into
# the query. This bounds how much is read for one, instead of the whole collection.
SEGMENT_SCAN_LIMIT = 5000
HIGH_VALUE_THRESHOLD = 10000
INACTIVE_DAYS = 60


async def _ensure_customer_access(tenant_id: str, user: dict):
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "customers")
    return tenant_oid


def normalize_customer_tags(tags: list[str] | None) -> list[str]:
    normalized = []
    seen = set()
    for tag in tags or []:
        clean = " ".join(str(tag).strip().split())
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(clean)
    return normalized


def _normalize_datetime(value):
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _derive_customer_segments(customer: dict) -> list[str]:
    stats = customer.get("stats", {}) or {}
    tags = [str(tag).lower() for tag in customer.get("tags", [])]
    created_at = customer.get("createdAt")
    last_activity = stats.get("lastActivityAt")
    segments = set()

    if stats.get("totalTransactions", 0) <= 1:
        segments.add("new")
    if stats.get("totalTransactions", 0) >= 2:
        segments.add("repeat")
    if float(stats.get("totalSpent", 0) or 0) >= HIGH_VALUE_THRESHOLD:
        segments.add("high_value")
    if customer.get("status") == "inactive":
        segments.add("inactive")
    if "vip" in tags:
        segments.add("vip")
    if "customer portal" in tags or "customer_portal" in tags:
        segments.add("customer_portal")
    if "website" in tags:
        segments.add("website")

    if last_activity:
        last_seen = _normalize_datetime(last_activity)
        if last_seen and last_seen < datetime.now(timezone.utc) - timedelta(days=INACTIVE_DAYS):
            segments.add("inactive")
    elif _normalize_datetime(created_at) and _normalize_datetime(created_at) < datetime.now(timezone.utc) - timedelta(days=INACTIVE_DAYS):
        segments.add("inactive")

    return sorted(segments)


def _customer_matches_segment(customer: dict, segment: str | None) -> bool:
    if not segment or segment == "all":
        return True
    return segment in _derive_customer_segments(customer)


def _decorate_customer(customer: dict) -> dict:
    public = serialize_document(customer)
    public["segments"] = _derive_customer_segments(customer)
    return public


async def _validate_customer_payload(tenant_id: str, payload, user: dict) -> dict:
    customer_type = getattr(payload, "type", None)
    customer_status = getattr(payload, "status", None)
    custom_fields = getattr(payload, "customFields", None) or {}

    if customer_type and customer_type not in ALLOWED_CUSTOMER_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid customer type.")

    if customer_status and customer_status not in ALLOWED_CUSTOMER_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid customer status.")

    validation = await validate_custom_values(tenant_id, "customers", "customer", custom_fields, user)
    if not validation["valid"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=validation["errors"])
    return validation["values"]


async def create_customer(tenant_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid = await _ensure_customer_access(tenant_id, user)
    await ensure_tenant_module_usage_available(tenant_oid, "customers")
    normalized_custom_fields = await _validate_customer_payload(tenant_id, payload, user)
    now = datetime.now(timezone.utc)

    customer_user_id = parse_object_id(payload.customerUserId, "customerUserId") if payload.customerUserId else None
    customer = {
        "tenantId": tenant_oid,
        "branchId": None,
        "customerUserId": customer_user_id,
        "type": payload.type,
        "name": payload.name,
        "phone": normalize_optional_pk_phone(payload.phone),
        "email": normalize_optional_email(payload.email),
        "address": payload.address,
        "status": payload.status,
        "tags": normalize_customer_tags(payload.tags),
        "customFields": normalized_custom_fields,
        "stats": {
            "totalTransactions": 0,
            "totalSpent": 0,
            "lastActivityAt": None,
        },
        "createdAt": now,
        "updatedAt": now,
    }
    customer["_id"] = (await db.customers.insert_one(customer)).inserted_id
    return _decorate_customer(customer)


async def list_customers(
    tenant_id: str,
    user: dict,
    search: str = "",
    status_filter: str | None = None,
    tag_filter: str | None = None,
    segment: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict:
    db = get_database()
    tenant_oid = await _ensure_customer_access(tenant_id, user)
    page = max(page, 1)
    limit = min(max(limit, 1), 100)

    query = {"tenantId": tenant_oid}
    if status_filter:
        query["status"] = status_filter
    if tag_filter:
        # Escaped like the search filter below. Unescaped, a crafted tag is regex
        # injection against this tenant's customer collection.
        query["tags"] = {"$regex": f"^{re.escape(tag_filter[:200])}$", "$options": "i"}
    if search:
        search = re.escape(search[:200])
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]

    # Segments are derived in Python from computed fields, so a segment filter still has
    # to read the matching set. Everything else paginates in the database: the previous
    # version loaded the tenant's whole customer collection on every page view, then
    # sliced it, then scanned it a second time for insights.
    if segment and segment != "all":
        matching = [
            customer
            async for customer in db.customers.find(query).sort("createdAt", -1).limit(SEGMENT_SCAN_LIMIT)
            if _customer_matches_segment(customer, segment)
        ]
        total = len(matching)
        start = (page - 1) * limit
        paged = matching[start : start + limit]
    else:
        total = await db.customers.count_documents(query)
        cursor = db.customers.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
        paged = [customer async for customer in cursor]

    # distinct() is answered from the index rather than by reading every document.
    unique_tags = sorted({str(tag) for tag in await db.customers.distinct("tags", {"tenantId": tenant_oid}) if tag}, key=str.lower)
    # Insights describe the whole collection, so they are identical on every page. They
    # were recomputed on each page view, scanning the collection a second time for a
    # figure the client already had. Page 1 carries them; later pages do not.
    insights = await get_customer_insights_for_tenant_oid(tenant_oid) if page <= 1 else None

    return {
        "items": [_decorate_customer(customer) for customer in paged],
        "filters": {
            "availableTags": unique_tags,
            "availableSegments": sorted(DEFAULT_SEGMENTS),
        },
        "insights": insights,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit,
        },
    }


async def get_customer(tenant_id: str, customer_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = await _ensure_customer_access(tenant_id, user)
    customer_oid = parse_object_id(customer_id, "customerId")
    customer = await db.customers.find_one({"_id": customer_oid, "tenantId": tenant_oid})
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return _decorate_customer(customer)


async def update_customer(tenant_id: str, customer_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid = await _ensure_customer_access(tenant_id, user)
    customer_oid = parse_object_id(customer_id, "customerId")
    existing = await db.customers.find_one({"_id": customer_oid, "tenantId": tenant_oid})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")

    update = {"updatedAt": datetime.now(timezone.utc)}
    for key in ["type", "name", "phone", "email", "address", "status"]:
        value = getattr(payload, key)
        if value is not None:
            if key == "phone":
                value = normalize_optional_pk_phone(value)
            elif key == "email":
                value = normalize_optional_email(value)
            update[key] = value

    if payload.tags is not None:
        update["tags"] = normalize_customer_tags(payload.tags)

    if payload.customerUserId is not None:
        update["customerUserId"] = parse_object_id(payload.customerUserId, "customerUserId") if payload.customerUserId else None

    if payload.customFields is not None:
        update["customFields"] = await _validate_customer_payload(tenant_id, payload, user)

    await db.customers.update_one({"_id": customer_oid, "tenantId": tenant_oid}, {"$set": update})
    return await get_customer(tenant_id, customer_id, user)


async def delete_customer(tenant_id: str, customer_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = await _ensure_customer_access(tenant_id, user)
    customer_oid = parse_object_id(customer_id, "customerId")
    result = await db.customers.update_one(
        {"_id": customer_oid, "tenantId": tenant_oid},
        {"$set": {"status": "inactive", "updatedAt": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")
    return await get_customer(tenant_id, customer_id, user)


async def get_customer_insights(tenant_id: str, user: dict) -> dict:
    tenant_oid = await _ensure_customer_access(tenant_id, user)
    return await get_customer_insights_for_tenant_oid(tenant_oid)


# Segment membership is computed per document by _derive_customer_segments, which is the
# single definition of what a segment means. Reproducing those rules in an aggregation
# would give two definitions that drift apart, so the documents are still read — but only
# the handful of fields the rules and the response actually touch, instead of whole
# customer records including addresses, notes and custom fields.
# Ceiling on the insights scan. Segment membership is computed per document, so the
# figures cannot be produced by an aggregation without duplicating those rules in a
# second place - which is the drift this codebase has been bitten by repeatedly.
INSIGHTS_SCAN_LIMIT = 5000

_INSIGHTS_PROJECTION = {
    "name": 1,
    "phone": 1,
    "tags": 1,
    "status": 1,
    "createdAt": 1,
    "stats": 1,
}


async def get_customer_insights_for_tenant_oid(tenant_oid: ObjectId) -> dict:
    db = get_database()
    # Bounded like the segment scan. The figures are a summary for a dashboard card, and
    # reading an unbounded collection on every first-page view is what the finding was
    # about; past the cap the numbers are reported as approximate rather than silently
    # wrong.
    customers = [
        customer
        async for customer in db.customers.find({"tenantId": tenant_oid}, _INSIGHTS_PROJECTION).limit(INSIGHTS_SCAN_LIMIT)
    ]
    decorated = [{"raw": customer, "segments": _derive_customer_segments(customer)} for customer in customers]
    total_customers = len(decorated)
    repeat_customers = [item for item in decorated if "repeat" in item["segments"]]
    high_value_customers = [item for item in decorated if "high_value" in item["segments"]]
    inactive_customers = [item for item in decorated if "inactive" in item["segments"]]
    top_repeat = sorted(
        decorated,
        key=lambda item: (item["raw"].get("stats", {}).get("totalTransactions", 0), item["raw"].get("stats", {}).get("totalSpent", 0)),
        reverse=True,
    )[:5]

    return {
        "summary": {
            "totalCustomers": total_customers,
            "repeatCustomers": len(repeat_customers),
            "repeatCustomerRate": round((len(repeat_customers) / total_customers) * 100, 1) if total_customers else 0,
            "highValueCustomers": len(high_value_customers),
            "inactiveCustomers": len(inactive_customers),
        },
        "segments": [
            {"code": "repeat", "label": "Repeat Customers", "count": len(repeat_customers)},
            {"code": "high_value", "label": "High Value", "count": len(high_value_customers)},
            {"code": "inactive", "label": "Inactive", "count": len(inactive_customers)},
        ],
        "topRepeatCustomers": [
            {
                "id": str(item["raw"]["_id"]),
                "name": item["raw"].get("name", ""),
                "phone": item["raw"].get("phone", ""),
                "totalTransactions": item["raw"].get("stats", {}).get("totalTransactions", 0),
                "totalSpent": item["raw"].get("stats", {}).get("totalSpent", 0),
                "segments": item["segments"],
            }
            for item in top_repeat
        ],
        "popularTags": [
            {"tag": tag, "count": count}
            for tag, count in sorted(
                {
                    tag: sum(1 for customer in customers if tag in customer.get("tags", []))
                    for tag in {tag for customer in customers for tag in customer.get("tags", [])}
                }.items(),
                key=lambda row: (-row[1], row[0].lower()),
            )[:10]
        ],
    }


async def find_or_create_customer_from_transaction(
    tenant: dict,
    *,
    customer_user_id: ObjectId | None = None,
    customer_profile_id: ObjectId | None = None,
    name: str = "",
    phone: str = "",
    email: str = "",
    address: dict | None = None,
    source_tag: str = "",
    email_verified: bool = False,
    phone_verified: bool = False,
) -> ObjectId:
    db = get_database()
    query = {"tenantId": tenant["_id"]}
    clauses = []
    if customer_user_id:
        clauses.append({"customerUserId": customer_user_id})
    # Matching a guest record by a contact detail attaches it to whoever is asking. The
    # danger is a REGISTERED account claiming a stranger's history by typing their phone
    # number into a profile, so the verification gate applies only when an account is
    # being attached. An anonymous order carrying its own phone number is the ordinary
    # de-duplication this function exists for, and gating that too meant a brand new
    # customer record on every single order.
    attaching_an_account = bool(customer_user_id)
    if email and (email_verified or not attaching_an_account):
        clauses.append({"email": email})
    if phone and (phone_verified or not attaching_an_account):
        clauses.append({"phone": phone})

    existing = None
    if clauses:
        existing = await db.customers.find_one({**query, "$or": clauses})
    if not existing:
        # A new customer record counts against the plan, however it came to be created.
        # Guarding only the manual route meant orders walked straight past the cap - the
        # same shape as the bulk item import bypass.
        from app.core.module_guard import ensure_tenant_module_usage_available

        try:
            await ensure_tenant_module_usage_available(tenant["_id"], "customers")
        except HTTPException:
            # An order must not fail because the business is at its customer limit; the
            # owner is told through the module screens. Reuse of an existing record is
            # unaffected because this only runs when there is none.
            logger.warning("Tenant %s is at its customer limit; recording the order anyway.", tenant.get("_id"))
    if existing:
        update = {"updatedAt": datetime.now(timezone.utc)}
        merged_tags = normalize_customer_tags([*(existing.get("tags", []) or []), source_tag] if source_tag else existing.get("tags", []))
        update["tags"] = merged_tags
        if customer_user_id and not existing.get("customerUserId"):
            update["customerUserId"] = customer_user_id
        if customer_profile_id and not existing.get("customerProfileId"):
            update["customerProfileId"] = customer_profile_id
        if name and not existing.get("name"):
            update["name"] = name
        if phone and not existing.get("phone"):
            update["phone"] = phone
        if email and not existing.get("email"):
            update["email"] = email
        if address and not existing.get("address"):
            update["address"] = address
        await db.customers.update_one({"_id": existing["_id"]}, {"$set": update})
        return existing["_id"]

    now = datetime.now(timezone.utc)
    customer = {
        "tenantId": tenant["_id"],
        "branchId": None,
        "customerUserId": customer_user_id,
        "customerProfileId": customer_profile_id,
        "type": "customer",
        "name": name or "Guest Customer",
        "phone": phone,
        "email": email or "",
        "address": address or {},
        "status": "active",
        "tags": normalize_customer_tags([source_tag] if source_tag else []),
        "customFields": {},
        "stats": {
            "totalTransactions": 0,
            "totalSpent": 0,
            "lastActivityAt": None,
        },
        "createdAt": now,
        "updatedAt": now,
    }
    customer["_id"] = (await db.customers.insert_one(customer)).inserted_id
    return customer["_id"]


async def ensure_customer_record_for_tenant(
    tenant: dict,
    *,
    customer_user_id: ObjectId,
    customer_profile_id: ObjectId | None = None,
    name: str = "",
    phone: str = "",
    email: str = "",
    address: dict | None = None,
    source_tag: str = "customer_portal",
    email_verified: bool = False,
    phone_verified: bool = False,
) -> ObjectId:
    return await find_or_create_customer_from_transaction(
        tenant,
        customer_user_id=customer_user_id,
        customer_profile_id=customer_profile_id,
        name=name,
        phone=phone,
        email=email,
        address=address,
        email_verified=email_verified,
        phone_verified=phone_verified,
        source_tag=source_tag,
    )


async def sync_registered_customer_records(
    *,
    customer_user_id: ObjectId,
    name: str = "",
    phone: str = "",
    email: str = "",
    address: dict | None = None,
    source_tag: str = "customer_portal",
    email_verified: bool = False,
    phone_verified: bool = False,
) -> int:
    db = get_database()
    # Records already linked to this account are always in scope.
    clauses = [{"customerUserId": customer_user_id}]
    # Matching a guest record by a contact detail CLAIMS that record, across every
    # tenant. Doing it on an unverified detail meant anyone could type a stranger's
    # phone number into their profile and take over that person's order history.
    # A detail is only used to claim once this account has actually proved it owns it.
    if email and email_verified:
        clauses.append({"email": email})
    if phone and phone_verified:
        clauses.append({"phone": phone})

    matches = [customer async for customer in db.customers.find({"$or": clauses})]
    if not matches:
        return 0

    updated_count = 0
    for customer in matches:
        update = {"updatedAt": datetime.now(timezone.utc)}
        is_linked_customer = customer.get("customerUserId") == customer_user_id
        update["tags"] = normalize_customer_tags([*(customer.get("tags", []) or []), source_tag] if source_tag else customer.get("tags", []))
        if not customer.get("customerUserId"):
            update["customerUserId"] = customer_user_id
        if name and (is_linked_customer or not customer.get("name") or customer.get("name") == "Guest Customer"):
            update["name"] = name
        if phone and (is_linked_customer or not customer.get("phone")):
            update["phone"] = phone
        if email and (is_linked_customer or not customer.get("email")):
            update["email"] = email
        if address and (is_linked_customer or not customer.get("address")):
            update["address"] = address
        # `status` is deliberately never written here. It is the business's decision
        # about this customer, and this function runs on the customer's own profile
        # save: reactivating meant anyone the business had marked inactive or blocked
        # could undo it simply by saving their profile.
        #
        # An unlinked record the business has shut off is not claimed at all, so a
        # customer cannot acquire someone else's blocked record by entering their
        # phone number or email.
        if not is_linked_customer and customer.get("status") in {"inactive", "blocked"}:
            continue
        await db.customers.update_one({"_id": customer["_id"]}, {"$set": update})
        updated_count += 1

    return updated_count


def _customer_source_tag(source: str | None) -> str:
    """How this customer first reached the business, for their record's tags."""
    known = {"customer_portal", "cashier", "imported", "ai_chat", "whatsapp"}
    normalized = str(source or "").strip().lower()
    return normalized if normalized in known else "website"


async def sync_customer_stats_for_transaction(tenant: dict, transaction: dict) -> ObjectId | None:
    db = get_database()
    customer_id = transaction.get("customerId")
    if not customer_id:
        customer_id = await find_or_create_customer_from_transaction(
            tenant,
            customer_user_id=transaction.get("customerUserId"),
            customer_profile_id=transaction.get("customerProfileId"),
            name=((transaction.get("customerSnapshot") or {}).get("name") or ""),
            phone=normalize_optional_pk_phone_or_blank((transaction.get("customerSnapshot") or {}).get("phone") or ""),
            email=normalize_optional_email((transaction.get("customerSnapshot") or {}).get("email") or ""),
            address=((transaction.get("fulfillment") or {}).get("address") or {}),
            source_tag=_customer_source_tag(transaction.get("source")),
        )

    await db.transactions.update_one({"_id": transaction["_id"]}, {"$set": {"customerId": customer_id}})
    transactions = [
        item
        async for item in db.transactions.find(
            {"tenantId": tenant["_id"], "customerId": customer_id}
        )
    ]
    total_spent = round(
        sum(float(item.get("pricing", {}).get("total", 0) or 0) for item in transactions if is_revenue_transaction(item)),
        2,
    )
    total_transactions = len(transactions)
    last_activity = max((item.get("createdAt") for item in transactions), default=None)

    await db.customers.update_one(
        {"_id": customer_id, "tenantId": tenant["_id"]},
        {
            "$set": {
                "stats.totalTransactions": total_transactions,
                "stats.totalSpent": total_spent,
                "stats.lastActivityAt": last_activity,
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    return customer_id
