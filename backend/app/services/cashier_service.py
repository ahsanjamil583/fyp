"""Owner-side management of cashier accounts.

A cashier is two documents: a row in ``users`` so the existing business login, JWT, and
session-version machinery work unchanged, and a row in ``cashiers`` holding the
tenant-scoped profile and permissions. The ``users`` row carries ``tenantId`` so every
authenticated request knows which business the cashier belongs to without a second
lookup, and ``cashiers`` is the record the owner edits.

Deactivating a cashier suspends the ``users`` row and bumps ``sessionVersion``, so an
already-issued token stops working immediately rather than at its next expiry.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.password_policy import validate_password_strength
from app.core.permissions import get_owned_tenant_or_403
from app.core.security import hash_password
from app.db.mongodb import get_database
from app.services.localization_service import normalize_optional_email, normalize_optional_pk_phone
from app.services.transaction_workflow_service import is_revenue_transaction

CASHIER_MODULE_CODE = "cashier"

DEFAULT_CASHIER_PERMISSIONS = {
    "canViewAllCashierOrders": False,
    "canAddCustomItems": True,
    "canApplyDiscount": True,
}


def normalize_cashier_permissions(permissions) -> dict:
    source = permissions.model_dump() if hasattr(permissions, "model_dump") else (permissions or {})
    return {key: bool(source.get(key, default)) for key, default in DEFAULT_CASHIER_PERMISSIONS.items()}


async def ensure_cashier_module(tenant_oid: ObjectId) -> None:
    await ensure_tenant_module_enabled(tenant_oid, CASHIER_MODULE_CODE)


async def ensure_owner_tenant(tenant_id: str, user: dict) -> tuple[ObjectId, dict]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_cashier_module(tenant_oid)
    return tenant_oid, tenant


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def cashier_public(cashier: dict, account: dict | None = None) -> dict:
    """Owner-facing projection. Never carries the password hash or raw user document."""
    data = serialize_document(cashier) or {}
    # The owner addresses a cashier by the profile id; the login row's id and the tenant
    # id are internal plumbing and have no business in a response.
    for internal in ("passwordHash", "userId", "tenantId", "createdBy"):
        data.pop(internal, None)
    data["permissions"] = normalize_cashier_permissions(cashier.get("permissions"))
    stats = cashier.get("stats") or {}
    data["stats"] = {
        "totalOrders": int(stats.get("totalOrders", 0) or 0),
        "totalSales": round(float(stats.get("totalSales", 0) or 0), 2),
        "lastOrderAt": _iso(stats.get("lastOrderAt")),
    }
    if account is not None:
        data["lastLoginAt"] = _iso(account.get("lastLoginAt"))
        data["accountStatus"] = account.get("status", "active")
        data["mustResetPassword"] = bool(account.get("mustResetPassword", False))
    return data


async def _recalculate_cashier_stats(tenant_oid: ObjectId, cashier_id: ObjectId) -> dict:
    db = get_database()
    orders = await db.transactions.find({"tenantId": tenant_oid, "cashier.cashierId": cashier_id}).to_list(length=None)
    total_sales = round(
        sum(float((order.get("pricing") or {}).get("total", 0) or 0) for order in orders if is_revenue_transaction(order)),
        2,
    )
    last_order_at = max((order.get("createdAt") for order in orders if order.get("createdAt")), default=None)
    stats = {"totalOrders": len(orders), "totalSales": total_sales, "lastOrderAt": last_order_at}
    await db.cashiers.update_one({"_id": cashier_id}, {"$set": {"stats": stats, "updatedAt": datetime.now(timezone.utc)}})
    return stats


async def list_cashiers(tenant_id: str, user: dict, active_only: bool | None = None) -> dict:
    db = get_database()
    tenant_oid, _ = await ensure_owner_tenant(tenant_id, user)

    query: dict = {"tenantId": tenant_oid}
    if active_only is True:
        query["isActive"] = True
    elif active_only is False:
        query["isActive"] = False

    cashiers = await db.cashiers.find(query).sort("createdAt", -1).to_list(length=200)
    user_ids = [row["userId"] for row in cashiers if row.get("userId")]
    accounts = {}
    async for account in db.users.find({"_id": {"$in": user_ids}}):
        accounts[account["_id"]] = account

    items = []
    for cashier in cashiers:
        stats = await _recalculate_cashier_stats(tenant_oid, cashier["_id"])
        items.append(cashier_public({**cashier, "stats": stats}, accounts.get(cashier.get("userId"))))

    active_count = sum(1 for row in items if row.get("isActive"))
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "active": active_count,
            "inactive": len(items) - active_count,
            "totalOrders": sum(int(row["stats"]["totalOrders"]) for row in items),
            "totalSales": round(sum(float(row["stats"]["totalSales"]) for row in items), 2),
        },
    }


async def create_cashier(tenant_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await ensure_owner_tenant(tenant_id, user)

    full_name = payload.fullName.strip()
    email = normalize_optional_email(payload.email or "")
    phone = normalize_optional_pk_phone(payload.phone or "")
    if not email and not phone:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A cashier needs an email or a phone number to sign in with.",
        )
    validate_password_strength(payload.password, email, phone, full_name)

    clauses = [clause for clause in ({"email": email} if email else None, {"phone": phone} if phone else None) if clause]
    if await db.users.find_one({"$or": clauses}):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email or phone already belongs to another BizXusAI account.",
        )

    now = datetime.now(timezone.utc)
    account = {
        "fullName": full_name,
        "passwordHash": hash_password(payload.password),
        "accountType": "cashier",
        "globalRole": "user",
        "tenantId": tenant_oid,
        "status": "active",
        "isEmailVerified": False,
        "isPhoneVerified": False,
        "mustResetPassword": False,
        "sessionVersion": 0,
        "lastLoginAt": None,
        "createdBy": user["_id"],
        "createdAt": now,
        "updatedAt": now,
    }
    if email:
        account["email"] = email
    # users.phone is a unique sparse index, which skips missing fields but not empty
    # strings: writing "" here made the second phone-less cashier a duplicate-key 500.
    if phone:
        account["phone"] = phone
    account["_id"] = (await db.users.insert_one(account)).inserted_id

    cashier = {
        "tenantId": tenant_oid,
        "userId": account["_id"],
        "fullName": full_name,
        "email": email,
        "phone": phone,
        "employeeCode": (payload.employeeCode or "").strip(),
        "isActive": True,
        "permissions": normalize_cashier_permissions(payload.permissions),
        "stats": {"totalOrders": 0, "totalSales": 0, "lastOrderAt": None},
        "createdBy": user["_id"],
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        cashier["_id"] = (await db.cashiers.insert_one(cashier)).inserted_id
    except Exception:
        # Never leave a login behind that no owner page can manage.
        await db.users.delete_one({"_id": account["_id"]})
        raise

    return {"cashier": cashier_public(cashier, account), "businessName": tenant.get("name", "")}


async def _get_cashier_or_404(tenant_oid: ObjectId, cashier_id: str) -> dict:
    db = get_database()
    cashier = await db.cashiers.find_one({"_id": parse_object_id(cashier_id, "cashierId"), "tenantId": tenant_oid})
    if not cashier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cashier not found for this business.")
    return cashier


async def get_cashier(tenant_id: str, cashier_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, _ = await ensure_owner_tenant(tenant_id, user)
    cashier = await _get_cashier_or_404(tenant_oid, cashier_id)
    stats = await _recalculate_cashier_stats(tenant_oid, cashier["_id"])
    account = await db.users.find_one({"_id": cashier["userId"]})
    return cashier_public({**cashier, "stats": stats}, account)


async def update_cashier(tenant_id: str, cashier_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, _ = await ensure_owner_tenant(tenant_id, user)
    cashier = await _get_cashier_or_404(tenant_oid, cashier_id)

    now = datetime.now(timezone.utc)
    cashier_update: dict = {"updatedAt": now}
    account_update: dict = {"updatedAt": now}
    account_unset: dict = {}

    if payload.fullName is not None:
        cashier_update["fullName"] = payload.fullName.strip()
        account_update["fullName"] = payload.fullName.strip()
    if payload.employeeCode is not None:
        cashier_update["employeeCode"] = payload.employeeCode.strip()
    if payload.permissions is not None:
        cashier_update["permissions"] = normalize_cashier_permissions(payload.permissions)

    if payload.phone is not None:
        phone = normalize_optional_pk_phone(payload.phone)
        if phone and await db.users.find_one({"phone": phone, "_id": {"$ne": cashier["userId"]}}):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That phone number already belongs to another account.")
        cashier_update["phone"] = phone
        if phone:
            account_update["phone"] = phone
        else:
            # Same reason as the cleared email below: users.phone is unique-sparse, so a
            # cleared number must be removed rather than stored as "", or the second
            # phone-less cashier collides with the first.
            account_unset["phone"] = ""

    if payload.email is not None:
        email = normalize_optional_email(payload.email)
        if email and await db.users.find_one({"email": email, "_id": {"$ne": cashier["userId"]}}):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email already belongs to another account.")
        cashier_update["email"] = email
        if email:
            account_update["email"] = email
        else:
            # The users index is unique-sparse, so a cleared email has to be removed
            # rather than stored as "" - several blanks would collide with each other.
            account_unset["email"] = ""

    remaining_login = cashier_update.get("email", cashier.get("email")) or cashier_update.get("phone", cashier.get("phone"))
    if not remaining_login:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A cashier needs an email or a phone number to sign in with.",
        )

    await db.cashiers.update_one({"_id": cashier["_id"]}, {"$set": cashier_update})
    account_doc: dict = {"$set": account_update}
    if account_unset:
        account_doc["$unset"] = account_unset
    await db.users.update_one({"_id": cashier["userId"]}, account_doc)

    updated = await db.cashiers.find_one({"_id": cashier["_id"]})
    account = await db.users.find_one({"_id": cashier["userId"]})
    return cashier_public(updated, account)


async def set_cashier_status(tenant_id: str, cashier_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, _ = await ensure_owner_tenant(tenant_id, user)
    cashier = await _get_cashier_or_404(tenant_oid, cashier_id)
    now = datetime.now(timezone.utc)
    is_active = bool(payload.isActive)

    await db.cashiers.update_one({"_id": cashier["_id"]}, {"$set": {"isActive": is_active, "updatedAt": now}})
    update_doc: dict = {"$set": {"status": "active" if is_active else "suspended", "updatedAt": now}}
    if not is_active:
        # Invalidate tokens already in the cashier's browser, not just future logins.
        update_doc["$inc"] = {"sessionVersion": 1}
    await db.users.update_one({"_id": cashier["userId"]}, update_doc)

    updated = await db.cashiers.find_one({"_id": cashier["_id"]})
    account = await db.users.find_one({"_id": cashier["userId"]})
    return cashier_public(updated, account)


async def reset_cashier_password(tenant_id: str, cashier_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, _ = await ensure_owner_tenant(tenant_id, user)
    cashier = await _get_cashier_or_404(tenant_oid, cashier_id)
    validate_password_strength(payload.password, cashier.get("email"), cashier.get("phone"), cashier.get("fullName"))
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": cashier["userId"]},
        {
            "$set": {
                "passwordHash": hash_password(payload.password),
                "mustResetPassword": bool(payload.mustChangeOnNextLogin),
                "updatedAt": now,
            },
            "$inc": {"sessionVersion": 1},
        },
    )
    await db.cashiers.update_one({"_id": cashier["_id"]}, {"$set": {"updatedAt": now}})
    updated = await db.cashiers.find_one({"_id": cashier["_id"]})
    account = await db.users.find_one({"_id": cashier["userId"]})
    return cashier_public(updated, account)


async def delete_cashier(tenant_id: str, cashier_id: str, user: dict) -> dict:
    """Retire a cashier without erasing the orders they created.

    The profile stays so historical receipts keep a name; only the login is withdrawn.
    """
    db = get_database()
    tenant_oid, _ = await ensure_owner_tenant(tenant_id, user)
    cashier = await _get_cashier_or_404(tenant_oid, cashier_id)
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": cashier["userId"]},
        {"$set": {"status": "disabled", "updatedAt": now}, "$inc": {"sessionVersion": 1}},
    )
    await db.cashiers.update_one(
        {"_id": cashier["_id"]},
        {"$set": {"isActive": False, "removedAt": now, "updatedAt": now}},
    )
    updated = await db.cashiers.find_one({"_id": cashier["_id"]})
    account = await db.users.find_one({"_id": cashier["userId"]})
    return cashier_public(updated, account)


async def get_cashier_context(account: dict) -> tuple[dict, dict]:
    """Resolve the signed-in cashier's profile and business, or refuse the request."""
    db = get_database()
    tenant_oid = account.get("tenantId")
    if isinstance(tenant_oid, str):
        tenant_oid = parse_object_id(tenant_oid, "tenantId")
    cashier = await db.cashiers.find_one({"tenantId": tenant_oid, "userId": account["_id"], "isActive": True})
    if not cashier:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This cashier account is not active for any business.")
    tenant = await db.tenants.find_one({"_id": tenant_oid})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found.")
    await ensure_cashier_module(tenant_oid)
    return cashier, tenant
