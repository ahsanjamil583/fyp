from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.tenant_service import audit_log

PLAN_DEFINITIONS = [
    {
        "code": "starter",
        "name": "Basic",
        "displayName": "Basic Free",
        "priceLabel": "Free",
        "isPaid": False,
        "description": "Free website, basic catalog/items, public website, simple dashboard, and manual orders/inquiries.",
    },
    {
        "code": "growth",
        "name": "AI Ordering",
        "displayName": "AI Ordering Free",
        "priceLabel": "Free",
        "isPaid": False,
        "description": "Customer portal, AI chat, RAG knowledge base, smart ordering, payments, and stock-aware ordering.",
    },
    {
        "code": "scale",
        "name": "Full Agent",
        "displayName": "Full Agent Free",
        "priceLabel": "Free",
        "isPaid": False,
        "description": "WhatsApp agent, owner AI assistant, daily reports, advanced agent tools, and full automation demo features.",
    },
]
PLAN_ORDER = [plan["code"] for plan in PLAN_DEFINITIONS]


async def list_modules() -> list[dict]:
    db = get_database()
    cursor = db.modules.find({"isActive": True}).sort("category", 1).sort("name", 1)
    return [serialize_document(module) async for module in cursor]


async def _get_active_module_map() -> dict[str, dict]:
    db = get_database()
    modules = await db.modules.find({"isActive": True}).to_list(length=200)
    return {module["code"]: module for module in modules}


def _resolve_dependency_chain(module_code: str, module_map: dict[str, dict], resolved: list[str] | None = None, seen: set[str] | None = None) -> list[str]:
    resolved = resolved or []
    seen = seen or set()
    if module_code in seen:
        return resolved
    seen.add(module_code)
    module = module_map.get(module_code)
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Required module '{module_code}' not found.")
    for dependency in module.get("dependencies", []):
        _resolve_dependency_chain(dependency, module_map, resolved, seen)
        if dependency not in resolved:
            resolved.append(dependency)
    return resolved


def _get_tenant_plan_code(tenant: dict) -> str:
    settings = tenant.get("settings", {}) or {}
    plan_code = str(settings.get("planCode") or "starter").lower()
    return plan_code if plan_code in PLAN_ORDER else "starter"


def get_plan_definition(plan_code: str | None) -> dict:
    normalized = str(plan_code or "starter").lower()
    return next((plan for plan in PLAN_DEFINITIONS if plan["code"] == normalized), PLAN_DEFINITIONS[0])


def get_package_access_status(tenant: dict, plan_code: str | None) -> str:
    return "approved"


def _get_included_plans(module: dict) -> list[str]:
    return list(PLAN_ORDER)


def _get_upgrade_plan_code(module: dict, current_plan: str) -> str | None:
    included_plans = _get_included_plans(module)
    if current_plan in included_plans:
        return None
    current_index = PLAN_ORDER.index(current_plan) if current_plan in PLAN_ORDER else 0
    for plan_code in PLAN_ORDER[current_index + 1 :]:
        if plan_code in included_plans:
            return plan_code
    return included_plans[0] if included_plans else None


def format_plan_name(plan_code: str | None) -> str:
    return get_plan_definition(plan_code).get("name", "Basic")


async def ensure_module_usage_capacity(tenant_oid, module_code: str, increment: int = 1) -> None:
    return None


def _ensure_module_plan_access(tenant: dict, module: dict, plan_code: str) -> None:
    return None


async def _enable_missing_free_modules(tenant: dict, modules: list[dict], user: dict) -> dict:
    db = get_database()
    tenant_oid = tenant["_id"]
    now = datetime.now(timezone.utc)
    active_codes = [module["code"] for module in modules]
    existing_codes = {
        row["moduleCode"]
        async for row in db.tenant_modules.find({"tenantId": tenant_oid, "moduleCode": {"$in": active_codes}})
    }
    missing_codes = [code for code in active_codes if code not in existing_codes]
    if not missing_codes:
        return tenant

    for code in missing_codes:
        await db.tenant_modules.update_one(
            {"tenantId": tenant_oid, "moduleCode": code},
            {
                "$set": {"status": "enabled", "updatedAt": now},
                "$setOnInsert": {"config": {}, "enabledBy": user["_id"], "enabledAt": now},
            },
            upsert=True,
        )
    await db.tenants.update_one(
        {"_id": tenant_oid},
        {"$addToSet": {"enabledModuleCodes": {"$each": missing_codes}}, "$set": {"updatedAt": now}},
    )
    return await db.tenants.find_one({"_id": tenant_oid}) or tenant


async def create_module(payload) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    if await db.modules.find_one({"code": payload.code}):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Module code already exists.")
    module = payload.model_dump()
    module["createdAt"] = now
    module["updatedAt"] = now
    module["_id"] = (await db.modules.insert_one(module)).inserted_id
    return serialize_document(module)


async def list_tenant_modules(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    modules = await list_modules()
    tenant = await _enable_missing_free_modules(tenant, modules, user)
    tenant_rows = {
        row["moduleCode"]: row
        async for row in db.tenant_modules.find({"tenantId": tenant_oid})
    }

    plan_code = _get_tenant_plan_code(tenant)
    enabled_codes = set(tenant.get("enabledModuleCodes", []))
    hydrated_modules = []
    for module in modules:
        included_plans = _get_included_plans(module)
        hydrated_modules.append(
            {
                **module,
                "tenantStatus": tenant_rows.get(module["code"], {}).get("status", "disabled"),
                "tenantConfig": tenant_rows.get(module["code"], {}).get("config", {}),
                "blockingDependents": [
                    other["code"]
                    for other in modules
                    if module["code"] in other.get("dependencies", []) and other["code"] in enabled_codes
                ],
                "planAccess": {
                    "currentPlan": plan_code,
                    "currentPlanName": format_plan_name(plan_code),
                    "includedPlans": included_plans,
                    "includedPlanNames": [format_plan_name(code) for code in included_plans],
                    "isIncluded": plan_code in included_plans,
                    "upgradePlanCode": _get_upgrade_plan_code(module, plan_code),
                    "upgradePlanName": format_plan_name(_get_upgrade_plan_code(module, plan_code)),
                    "accessStatus": get_package_access_status(tenant, plan_code),
                },
            }
        )

    return {
        "tenant": serialize_document(tenant),
        "tenantPlan": {**get_plan_definition(plan_code), "accessStatus": get_package_access_status(tenant, plan_code)},
        "plans": PLAN_DEFINITIONS,
        "modules": hydrated_modules,
    }


async def enable_tenant_module(tenant_id: str, module_code: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    module_map = await _get_active_module_map()
    module = module_map.get(module_code)
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    plan_code = _get_tenant_plan_code(tenant)
    _ensure_module_plan_access(tenant, module, plan_code)
    dependency_codes = _resolve_dependency_chain(module_code, module_map)
    codes_to_enable = dependency_codes + [module_code]
    for dependency_code in dependency_codes:
        _ensure_module_plan_access(tenant, module_map[dependency_code], plan_code)
    now = datetime.now(timezone.utc)
    for code in codes_to_enable:
        await db.tenant_modules.update_one(
            {"tenantId": tenant_oid, "moduleCode": code},
            {
                "$set": {"status": "enabled", "updatedAt": now},
                "$setOnInsert": {
                    "config": {},
                    "enabledBy": user["_id"],
                    "enabledAt": now,
                },
            },
            upsert=True,
        )
    await db.tenants.update_one(
        {"_id": tenant_oid},
        {"$addToSet": {"enabledModuleCodes": {"$each": codes_to_enable}}, "$set": {"updatedAt": now}},
    )
    await audit_log(
        "tenant_module_enabled",
        user["_id"],
        tenant_oid,
        {"moduleCode": module_code, "autoEnabledDependencies": dependency_codes, "planCode": plan_code},
    )
    return await list_tenant_modules(tenant_id, user)


async def disable_tenant_module(tenant_id: str, module_code: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    module_map = await _get_active_module_map()
    module = module_map.get(module_code)
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")
    enabled_codes = set(tenant.get("enabledModuleCodes", []))
    blocking_dependents = [
        candidate["name"]
        for candidate in module_map.values()
        if module_code in candidate.get("dependencies", []) and candidate["code"] in enabled_codes
    ]
    if blocking_dependents:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Disable dependent modules first: {', '.join(blocking_dependents)}.",
        )
    now = datetime.now(timezone.utc)
    await db.tenant_modules.update_one(
        {"tenantId": tenant_oid, "moduleCode": module_code},
        {"$set": {"status": "disabled", "updatedAt": now}},
        upsert=False,
    )
    await db.tenants.update_one(
        {"_id": tenant_oid},
        {"$pull": {"enabledModuleCodes": module_code}, "$set": {"updatedAt": now}},
    )
    await audit_log("tenant_module_disabled", user["_id"], tenant_oid, {"moduleCode": module_code})
    return await list_tenant_modules(tenant_id, user)


async def update_tenant_module_config(tenant_id: str, module_code: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)
    result = await db.tenant_modules.update_one(
        {"tenantId": tenant_oid, "moduleCode": module_code, "status": "enabled"},
        {"$set": {"config": payload.config, "updatedAt": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enabled tenant module not found.")
    return await list_tenant_modules(tenant_id, user)
