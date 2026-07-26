from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.db.mongodb import get_database
from app.services.auth_service import user_public
from app.services.category_config_service import apply_category_default_custom_fields, build_tenant_category_hints
from app.services.module_service import PLAN_ORDER
from app.services.onboarding_service import LAUNCH_PROFILES, normalize_launch_profile
from app.services.tenant_service import (
    _get_active_business_category,
    _merge_tenant_settings,
    _normalize_address,
    _normalize_contact,
    _normalize_website_settings,
    _validate_plan_change,
)

PAID_PLAN_LABELS = {"growth": "AI Ordering", "scale": "Full Agent"}


def _serialize_admin_user(user: dict, owned_tenant_count: int = 0) -> dict:
    data = user_public(user)
    data["ownedTenantCount"] = owned_tenant_count
    data["createdAt"] = user.get("createdAt")
    data["updatedAt"] = user.get("updatedAt")
    data["lastLoginAt"] = user.get("lastLoginAt")
    return data


async def _owner_counts_by_user(db) -> dict[str, int]:
    rows = await db.tenants.aggregate([{"$group": {"_id": "$ownerUserId", "count": {"$sum": 1}}}]).to_list(length=500)
    return {str(row["_id"]): int(row["count"]) for row in rows if row.get("_id")}


async def _build_tenant_relations(db, tenants: list[dict]) -> tuple[dict[str, dict], dict[str, dict], dict[str, int]]:
    owner_ids = sorted({tenant.get("ownerUserId") for tenant in tenants if tenant.get("ownerUserId")}, key=str)
    category_ids = sorted({tenant.get("businessCategoryId") for tenant in tenants if tenant.get("businessCategoryId")}, key=str)
    tenant_ids = [tenant["_id"] for tenant in tenants]

    owners = await db.users.find({"_id": {"$in": owner_ids}}).to_list(length=max(len(owner_ids), 1))
    categories = await db.business_categories.find({"_id": {"$in": category_ids}}).to_list(length=max(len(category_ids), 1))
    module_rows = await db.tenant_modules.aggregate(
        [
            {"$match": {"tenantId": {"$in": tenant_ids}, "status": "enabled"}},
            {"$group": {"_id": "$tenantId", "count": {"$sum": 1}}},
        ]
    ).to_list(length=max(len(tenant_ids), 1))

    owner_map = {str(owner["_id"]): owner for owner in owners}
    category_map = {str(category["_id"]): category for category in categories}
    module_count_map = {str(row["_id"]): int(row["count"]) for row in module_rows}
    return owner_map, category_map, module_count_map


def _tenant_upgrade_requests(tenant: dict) -> list[dict]:
    settings = tenant.get("settings") or {}
    package_access = settings.get("packageAccess") or {}
    rows = []
    for plan_code, access in package_access.items():
        if not isinstance(access, dict):
            continue
        status_value = str(access.get("status") or "locked").lower()
        if status_value == "locked":
            continue
        profile_code = normalize_launch_profile(access.get("profileCode"))
        profile = LAUNCH_PROFILES.get(profile_code) or {}
        rows.append(
            {
                "planCode": plan_code,
                "planName": PAID_PLAN_LABELS.get(plan_code, plan_code),
                "profileCode": profile_code,
                "profileName": profile.get("name") or PAID_PLAN_LABELS.get(plan_code, plan_code),
                "status": status_value,
                "requestedAt": access.get("requestedAt"),
                "requestedBy": access.get("requestedBy"),
                "paymentMode": access.get("paymentMode", ""),
                "decidedAt": access.get("decidedAt"),
                "decidedBy": access.get("decidedBy"),
                "decisionNote": access.get("decisionNote", ""),
            }
        )
    return sorted(rows, key=lambda row: row.get("requestedAt") or "", reverse=True)


def _resolve_profile_modules(profile_modules: list[str], module_map: dict[str, dict]) -> list[str]:
    resolved: list[str] = []

    def add_with_dependencies(module_code: str) -> None:
        module = module_map.get(module_code)
        if not module:
            return
        for dependency in module.get("dependencies", []) or []:
            add_with_dependencies(dependency)
        if module_code not in resolved:
            resolved.append(module_code)

    for code in profile_modules:
        add_with_dependencies(code)
    return resolved


async def list_admin_users() -> list[dict]:
    db = get_database()
    owner_counts = await _owner_counts_by_user(db)
    users = await db.users.find({}).sort("createdAt", -1).to_list(length=500)
    return [_serialize_admin_user(user, owner_counts.get(str(user["_id"]), 0)) for user in users]


async def update_admin_user(user_id: str, payload, current_user: dict) -> dict:
    db = get_database()
    user_oid = parse_object_id(user_id, "userId")
    user = await db.users.find_one({"_id": user_oid})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    update = {"updatedAt": datetime.now(timezone.utc)}
    for key in ["status", "globalRole", "isEmailVerified", "isPhoneVerified"]:
        value = getattr(payload, key)
        if value is not None:
            update[key] = value

    if str(current_user["_id"]) == user_id:
        if update.get("globalRole") == "user" or update.get("status") == "suspended":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You cannot remove your own platform admin access or suspend your own account.",
            )

    await db.users.update_one({"_id": user_oid}, {"$set": update})
    owner_counts = await _owner_counts_by_user(db)
    updated_user = await db.users.find_one({"_id": user_oid})
    return _serialize_admin_user(updated_user, owner_counts.get(str(user_oid), 0))


async def list_admin_tenants() -> list[dict]:
    db = get_database()
    tenants = await db.tenants.find({}).sort("createdAt", -1).to_list(length=500)
    owner_map, category_map, module_count_map = await _build_tenant_relations(db, tenants)
    rows = []
    for tenant in tenants:
        item = serialize_document(tenant)
        owner = owner_map.get(str(tenant.get("ownerUserId")))
        category = category_map.get(str(tenant.get("businessCategoryId")))
        item["owner"] = _serialize_admin_user(owner) if owner else None
        item["businessCategory"] = serialize_document(category) if category else None
        item["enabledModuleCount"] = module_count_map.get(str(tenant["_id"]), len(tenant.get("enabledModuleCodes", [])))
        item["upgradeRequests"] = _tenant_upgrade_requests(tenant)
        item["pendingUpgradeCount"] = len([request for request in item["upgradeRequests"] if request["status"] == "pending_approval"])
        rows.append(item)
    return rows


async def decide_admin_package_upgrade(tenant_id: str, plan_code: str, payload, current_user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await db.tenants.find_one({"_id": tenant_oid})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    normalized_plan = str(plan_code or "").strip().lower()
    if normalized_plan not in {"growth", "scale"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only paid package requests can be approved or rejected.")

    settings = dict(tenant.get("settings") or {})
    package_access = dict(settings.get("packageAccess") or {})
    access = dict(package_access.get(normalized_plan) or {})
    if not access or str(access.get("status") or "").lower() != "pending_approval":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending upgrade request found for this package.")

    now = datetime.now(timezone.utc)
    decision_status = payload.status
    access.update(
        {
            "status": decision_status,
            "decidedAt": now.isoformat(),
            "decidedBy": str(current_user.get("_id")),
            "decisionNote": (payload.note or "").strip(),
        }
    )
    package_access[normalized_plan] = access
    settings["packageAccess"] = package_access
    settings.setdefault("onboarding", {}).setdefault("phase28", {})
    phase28 = settings["onboarding"]["phase28"]
    phase28.update(
        {
            "targetPlan": normalized_plan,
            "upgradeStatus": decision_status,
            "upgradeDecidedAt": now.isoformat(),
            "upgradeDecisionNote": access["decisionNote"],
        }
    )

    enabled_codes = []
    if decision_status == "approved":
        profile_code = normalize_launch_profile(access.get("profileCode"))
        profile = LAUNCH_PROFILES.get(profile_code) or {}
        settings["planCode"] = normalized_plan
        phase28.update({"profileCode": profile_code, "profileName": profile.get("name", PAID_PLAN_LABELS.get(normalized_plan, normalized_plan))})

        modules = await db.modules.find({"isActive": True}).to_list(length=300)
        module_map = {module["code"]: module for module in modules}
        enabled_codes = _resolve_profile_modules(profile.get("modules") or [], module_map)
        for code in enabled_codes:
            await db.tenant_modules.update_one(
                {"tenantId": tenant_oid, "moduleCode": code},
                {
                    "$set": {"status": "enabled", "updatedAt": now},
                    "$setOnInsert": {"config": {}, "enabledBy": current_user.get("_id"), "enabledAt": now},
                },
                upsert=True,
            )

    update_doc = {"settings": settings, "updatedAt": now}
    tenant_update = {"$set": update_doc}
    if enabled_codes:
        tenant_update["$addToSet"] = {"enabledModuleCodes": {"$each": enabled_codes}}
    await db.tenants.update_one({"_id": tenant_oid}, tenant_update)
    await db.audit_logs.insert_one(
        {
            "action": "tenant_package_upgrade_decided",
            "actorUserId": current_user.get("_id"),
            "tenantId": tenant_oid,
            "metadata": {
                "planCode": normalized_plan,
                "status": decision_status,
                "enabledModules": enabled_codes,
                "note": access["decisionNote"],
            },
            "createdAt": now,
        }
    )

    refreshed = await list_admin_tenants()
    return next((item for item in refreshed if item["id"] == tenant_id), serialize_document(await db.tenants.find_one({"_id": tenant_oid})))


async def update_admin_tenant(tenant_id: str, payload) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    existing = await db.tenants.find_one({"_id": tenant_oid})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    update = {"updatedAt": datetime.now(timezone.utc)}
    for key in ["name", "description", "contact", "address", "settings", "websiteSettings", "status", "websiteStatus"]:
        value = getattr(payload, key)
        if value is not None:
            if key == "contact":
                value = _normalize_contact(value)
            elif key == "address":
                value = _normalize_address(value)
            update[key] = value

    category = None
    if payload.businessCategoryId is not None:
        category = await _get_active_business_category(payload.businessCategoryId)
        update["businessCategoryId"] = category["_id"] if category else None

    merged_snapshot = {**existing, **update}
    update["settings"] = _merge_tenant_settings(existing.get("settings"), update.get("settings"), merged_snapshot)
    await _validate_plan_change(existing, update["settings"])

    if category:
        update["settings"]["categoryHints"] = build_tenant_category_hints(category)

    if payload.websiteSettings is not None:
        merged_website_settings = {**(existing.get("websiteSettings") or {}), **(payload.websiteSettings or {})}
        update["websiteSettings"] = _normalize_website_settings(merged_website_settings, update.get("name") or existing.get("name", "Business"))
    elif "websiteSettings" in update:
        update["websiteSettings"] = _normalize_website_settings(update["websiteSettings"], update.get("name") or existing.get("name", "Business"))

    await db.tenants.update_one({"_id": tenant_oid}, {"$set": update})
    if category:
        await apply_category_default_custom_fields(tenant_oid, category)
    refreshed = await list_admin_tenants()
    return next((tenant for tenant in refreshed if tenant["id"] == tenant_id), serialize_document(await db.tenants.find_one({"_id": tenant_oid})))


async def list_admin_modules() -> list[dict]:
    db = get_database()
    modules = await db.modules.find({}).sort("category", 1).sort("name", 1).to_list(length=500)
    usage = await db.tenant_modules.aggregate(
        [
            {"$match": {"status": "enabled"}},
            {"$group": {"_id": "$moduleCode", "enabledTenantCount": {"$addToSet": "$tenantId"}}},
        ]
    ).to_list(length=500)
    usage_map = {row["_id"]: len(row.get("enabledTenantCount", [])) for row in usage}
    return [{**serialize_document(module), "enabledTenantCount": usage_map.get(module["code"], 0)} for module in modules]


async def get_admin_payments() -> dict:
    db = get_database()
    records = await db.payment_records.find({}).sort("createdAt", -1).to_list(length=100)
    tenant_ids = sorted({record.get("tenantId") for record in records if record.get("tenantId")}, key=str)
    tenants = await db.tenants.find({"_id": {"$in": tenant_ids}}).to_list(length=max(len(tenant_ids), 1))
    tenant_map = {tenant["_id"]: tenant for tenant in tenants}
    events = await db.stripe_webhook_events.find({}).sort("createdAt", -1).to_list(length=50)
    payment_rows = []
    for record in records:
        tenant = tenant_map.get(record.get("tenantId")) or {}
        row = serialize_document(record)
        row["tenant"] = {"id": str(tenant.get("_id", "")), "name": tenant.get("name", "Unknown"), "slug": tenant.get("slug", "")}
        payment_rows.append(row)

    stripe_paid = [record for record in records if record.get("provider") == "stripe" and record.get("status") in {"paid", "completed"}]
    stripe_pending = [record for record in records if record.get("provider") == "stripe" and record.get("status") in {"pending_verification", "pending"}]
    failed_events = [event for event in events if event.get("status") == "failed"]
    return {
        "summary": {
            "totalPaymentRecords": len(records),
            "stripePaidAmount": sum(float(record.get("amount", 0) or 0) for record in stripe_paid),
            "stripePendingAmount": sum(float(record.get("amount", 0) or 0) for record in stripe_pending),
            "stripePaidCount": len(stripe_paid),
            "stripePendingCount": len(stripe_pending),
            "webhookEvents": len(events),
            "failedWebhookEvents": len(failed_events),
        },
        "records": payment_rows,
        "stripeWebhookEvents": [serialize_document(event) for event in events],
    }


async def update_admin_module(module_code: str, payload) -> dict:
    db = get_database()
    existing = await db.modules.find_one({"code": module_code})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    update = {"updatedAt": datetime.now(timezone.utc)}
    for key in [
        "name",
        "description",
        "category",
        "isActive",
        "dependencies",
        "permissions",
        "configSchema",
        "frontendRoutes",
        "apiPrefix",
        "aiTools",
        "availability",
        "usageLimits",
    ]:
        value = getattr(payload, key)
        if value is not None:
            update[key] = value

    await db.modules.update_one({"code": module_code}, {"$set": update})
    modules = await list_admin_modules()
    return next((module for module in modules if module["code"] == module_code), serialize_document(await db.modules.find_one({"code": module_code})))


async def get_admin_overview() -> dict:
    db = get_database()
    total_users = await db.users.count_documents({})
    active_users = await db.users.count_documents({"status": "active"})
    total_tenants = await db.tenants.count_documents({})
    active_tenants = await db.tenants.count_documents({"status": "active"})
    published_tenants = await db.tenants.count_documents({"websiteStatus": "published"})
    total_categories = await db.business_categories.count_documents({})
    active_categories = await db.business_categories.count_documents({"isActive": True})
    total_modules = await db.modules.count_documents({})
    active_modules = await db.modules.count_documents({"isActive": True})

    plan_rows = await db.tenants.aggregate(
        [
            {"$group": {"_id": "$settings.planCode", "count": {"$sum": 1}}},
        ]
    ).to_list(length=20)
    plan_breakdown = {plan_code: 0 for plan_code in PLAN_ORDER}
    for row in plan_rows:
        plan_code = str(row.get("_id") or "starter").lower()
        if plan_code in plan_breakdown:
            plan_breakdown[plan_code] = int(row["count"])

    category_rows = await db.tenants.aggregate(
        [
            {"$match": {"businessCategoryId": {"$ne": None}}},
            {"$group": {"_id": "$businessCategoryId", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 6},
        ]
    ).to_list(length=6)
    category_ids = [row["_id"] for row in category_rows if row.get("_id")]
    categories = await db.business_categories.find({"_id": {"$in": category_ids}}).to_list(length=max(len(category_ids), 1))
    category_map = {category["_id"]: category for category in categories}

    module_rows = await db.tenant_modules.aggregate(
        [
            {"$match": {"status": "enabled"}},
            {"$group": {"_id": "$moduleCode", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8},
        ]
    ).to_list(length=8)

    since = datetime.now(timezone.utc) - timedelta(days=7)
    new_users_7d = await db.users.count_documents({"createdAt": {"$gte": since}})
    new_tenants_7d = await db.tenants.count_documents({"createdAt": {"$gte": since}})

    recent_users = await db.users.find({}).sort("createdAt", -1).to_list(length=5)
    recent_tenants = await list_admin_tenants()

    return {
        "summary": {
            "users": {"total": total_users, "active": active_users, "newLast7Days": new_users_7d},
            "tenants": {"total": total_tenants, "active": active_tenants, "published": published_tenants, "newLast7Days": new_tenants_7d},
            "categories": {"total": total_categories, "active": active_categories},
            "modules": {"total": total_modules, "active": active_modules},
        },
        "planBreakdown": plan_breakdown,
        "topCategories": [
            {
                "id": str(row["_id"]),
                "name": category_map.get(row["_id"], {}).get("name", "Unknown"),
                "count": int(row["count"]),
            }
            for row in category_rows
        ],
        "topModules": [{"code": row["_id"], "count": int(row["count"])} for row in module_rows],
        "recentUsers": [_serialize_admin_user(user) for user in recent_users],
        "recentTenants": recent_tenants[:5],
    }


async def get_admin_reports() -> dict:
    overview = await get_admin_overview()
    db = get_database()

    role_rows = await db.users.aggregate(
        [
            {"$group": {"_id": "$globalRole", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
    ).to_list(length=20)
    website_rows = await db.tenants.aggregate(
        [
            {"$group": {"_id": "$websiteStatus", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
    ).to_list(length=20)
    module_catalog = await list_admin_modules()

    return {
        **overview,
        "userRoleBreakdown": [{"role": str(row.get("_id") or "unknown"), "count": int(row["count"])} for row in role_rows],
        "websiteStatusBreakdown": [{"status": str(row.get("_id") or "unknown"), "count": int(row["count"])} for row in website_rows],
        "moduleCatalog": module_catalog,
    }
