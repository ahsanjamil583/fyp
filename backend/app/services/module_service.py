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
        "displayName": "AI Ordering Paid",
        "priceLabel": "Paid",
        "isPaid": True,
        "description": "Adds customer portal, AI chat, RAG knowledge base, smart ordering, payments, and stock-aware ordering.",
    },
    {
        "code": "scale",
        "name": "Full Agent",
        "displayName": "Full Agent Paid",
        "priceLabel": "Paid",
        "isPaid": True,
        "description": "Adds WhatsApp agent, owner AI assistant, daily reports, advanced agent tools, and full automation demo features.",
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
    plan = get_plan_definition(plan_code)
    if not plan.get("isPaid"):
        return "approved"
    if _get_tenant_plan_code(tenant) == plan["code"]:
        return "approved"
    settings = tenant.get("settings", {}) or {}
    access = ((settings.get("packageAccess") or {}).get(plan["code"]) or {})
    return str(access.get("status") or "locked").lower()


def _get_included_plans(module: dict) -> list[str]:
    availability = module.get("availability", {}) or {}
    included_plans = availability.get("includedPlans") or PLAN_ORDER
    return [plan for plan in included_plans if plan in PLAN_ORDER] or PLAN_ORDER


def _get_upgrade_plan_code(module: dict, current_plan: str) -> str | None:
    included_plans = _get_included_plans(module)
    if current_plan in included_plans:
        return None
    for plan_code in PLAN_ORDER:
        if plan_code in included_plans:
            return plan_code
    return None


def format_plan_name(plan_code: str | None) -> str:
    return get_plan_definition(plan_code).get("name", "Basic")


def _get_usage_limit_config(module: dict, plan_code: str) -> dict | None:
    usage_limits = module.get("usageLimits", {}) or {}
    config = usage_limits.get(plan_code)
    return config if isinstance(config, dict) else None


async def _get_usage_current_value(db, tenant_oid, metric_code: str) -> int:
    if metric_code == "customers":
        return await db.customers.count_documents({"tenantId": tenant_oid})
    if metric_code == "active_items":
        return await db.items.count_documents({"tenantId": tenant_oid, "status": {"$ne": "archived"}})
    if metric_code == "monthly_ai_messages":
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        return await db.messages.count_documents(
            {
                "tenantId": tenant_oid,
                "sender": "customer",
                "createdAt": {"$gte": month_start},
            }
        )
    if metric_code == "monthly_whatsapp_messages":
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        return await db.whatsapp_message_logs.count_documents(
            {
                "tenantId": tenant_oid,
                "direction": "inbound",
                "createdAt": {"$gte": month_start},
            }
        )
    return 0


async def build_module_usage_summary(module: dict, tenant_oid, plan_code: str) -> dict | None:
    config = _get_usage_limit_config(module, plan_code)
    if not config:
        return None
    db = get_database()
    current = await _get_usage_current_value(db, tenant_oid, str(config.get("metricCode", "")))
    limit = config.get("limit")
    unlimited = limit is None
    remaining = None if unlimited else max(int(limit) - current, 0)
    if unlimited:
        status_label = "ok"
    elif current >= int(limit):
        status_label = "limit_reached"
    elif current >= max(int(limit) - 5, int(limit * 0.8)):
        status_label = "near_limit"
    else:
        status_label = "ok"
    return {
        "metricCode": config.get("metricCode", ""),
        "label": config.get("label", "Usage"),
        "current": current,
        "limit": limit,
        "remaining": remaining,
        "status": status_label,
    }


async def ensure_module_usage_capacity(tenant_oid, module_code: str, increment: int = 1) -> None:
    db = get_database()
    tenant = await db.tenants.find_one({"_id": tenant_oid})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    module = await db.modules.find_one({"code": module_code, "isActive": True})
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    plan_code = _get_tenant_plan_code(tenant)
    usage = await build_module_usage_summary(module, tenant_oid, plan_code)
    if not usage or usage.get("limit") is None:
        return

    if usage["current"] + max(increment, 0) > int(usage["limit"]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{module.get('name', 'Module')} limit reached for the {plan_code} plan. Upgrade your workspace plan to continue.",
        )


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
    tenant_rows = {
        row["moduleCode"]: row
        async for row in db.tenant_modules.find({"tenantId": tenant_oid})
    }

    plan_code = _get_tenant_plan_code(tenant)
    enabled_codes = set(tenant.get("enabledModuleCodes", []))
    hydrated_modules = []
    for module in modules:
        included_plans = _get_included_plans(module)
        usage_summary = await build_module_usage_summary(module, tenant_oid, plan_code)
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
                "usageSummary": usage_summary,
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
    dependency_codes = _resolve_dependency_chain(module_code, module_map)
    codes_to_enable = dependency_codes + [module_code]
    blocked_modules = [code for code in codes_to_enable if plan_code not in _get_included_plans(module_map[code])]
    if blocked_modules:
        blocked_names = [module_map[code]["name"] for code in blocked_modules]
        upgrade_code = _get_upgrade_plan_code(module_map[blocked_modules[0]], plan_code)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This feature is available in the {format_plan_name(upgrade_code)} plan. Please upgrade to continue. Locked modules: {', '.join(blocked_names)}.",
        )

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
