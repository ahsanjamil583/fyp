from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.db.mongodb import get_database

PLAN_ORDER = ["starter", "growth", "scale"]


def _get_tenant_plan_code(tenant: dict) -> str:
    settings = tenant.get("settings", {}) or {}
    plan_code = str(settings.get("planCode") or "starter").lower()
    return plan_code if plan_code in PLAN_ORDER else "starter"


def _get_included_plans(module: dict) -> list[str]:
    availability = module.get("availability", {}) or {}
    included_plans = availability.get("includedPlans") or PLAN_ORDER
    return [plan for plan in included_plans if plan in PLAN_ORDER] or PLAN_ORDER


def _get_usage_limit_config(module: dict, plan_code: str) -> dict | None:
    usage_limits = module.get("usageLimits", {}) or {}
    config = usage_limits.get(plan_code)
    return config if isinstance(config, dict) else None


async def _get_usage_current_value(db, tenant_id, metric_code: str) -> int:
    if metric_code == "customers":
        return await db.customers.count_documents({"tenantId": tenant_id})
    if metric_code == "active_items":
        return await db.items.count_documents({"tenantId": tenant_id, "status": {"$ne": "archived"}})
    if metric_code == "monthly_ai_messages":
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        return await db.messages.count_documents(
            {
                "tenantId": tenant_id,
                "sender": "customer",
                "createdAt": {"$gte": month_start},
            }
        )
    if metric_code == "monthly_whatsapp_messages":
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        return await db.whatsapp_message_logs.count_documents(
            {
                "tenantId": tenant_id,
                "direction": "inbound",
                "createdAt": {"$gte": month_start},
            }
        )
    return 0


async def ensure_tenant_module_enabled(tenant_id: ObjectId, module_code: str) -> None:
    db = get_database()
    module = await db.modules.find_one({"code": module_code, "isActive": True})
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    tenant_module = await db.tenant_modules.find_one(
        {"tenantId": tenant_id, "moduleCode": module_code, "status": "enabled"}
    )
    if not tenant_module:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Module is disabled for this tenant.")

    tenant = await db.tenants.find_one({"_id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    plan_code = _get_tenant_plan_code(tenant)
    if plan_code not in _get_included_plans(module):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Module is not available on the current '{plan_code}' plan.",
        )


async def ensure_tenant_module_usage_available(tenant_id: ObjectId, module_code: str, increment: int = 1) -> None:
    db = get_database()
    tenant = await db.tenants.find_one({"_id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")

    module = await db.modules.find_one({"code": module_code, "isActive": True})
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    plan_code = _get_tenant_plan_code(tenant)
    config = _get_usage_limit_config(module, plan_code)
    if not config:
        return

    limit = config.get("limit")
    if limit is None:
        return

    current = await _get_usage_current_value(db, tenant_id, str(config.get("metricCode", "")))
    if current + max(increment, 0) > int(limit):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{module.get('name', 'Module')} limit reached for the {plan_code} plan. Upgrade your workspace plan to continue.",
        )
