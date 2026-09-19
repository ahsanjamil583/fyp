from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.mongodb import get_database

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

    if not await db.tenants.find_one({"_id": tenant_id}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")


async def ensure_tenant_ai_budget(tenant_id: ObjectId) -> None:
    """Cap billed AI replies per tenant per day.

    The plan limits cover a month, which is too coarse to stop a single bad day from
    consuming the whole allowance: the public chat endpoint needs no account, so one
    script can exhaust a month's budget in an afternoon. This is the daily ceiling.
    """
    if settings.ai_daily_message_cap <= 0:
        return

    db = get_database()
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    used_today = await db.messages.count_documents(
        {"tenantId": tenant_id, "sender": "customer", "createdAt": {"$gte": day_start}}
    )
    if used_today >= settings.ai_daily_message_cap:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "This business has reached its daily AI assistant limit. "
                "Please try again tomorrow or contact the business directly."
            ),
        )


# How each usage metric declared in the module seeds is actually counted. A metric with
# no entry here cannot be enforced, and is treated as unlimited rather than as zero.
_USAGE_COUNTERS: dict[str, dict] = {
    "active_items": {
        "collection": "items",
        "filter": lambda tenant_id, _start: {"tenantId": tenant_id, "status": "active"},
    },
    "customers": {
        "collection": "customers",
        "filter": lambda tenant_id, _start: {"tenantId": tenant_id},
    },
    "monthly_ai_messages": {
        "collection": "messages",
        "filter": lambda tenant_id, start: {"tenantId": tenant_id, "sender": "customer", "createdAt": {"$gte": start}},
    },
    "monthly_owner_agent_messages": {
        "collection": "owner_agent_messages",
        "filter": lambda tenant_id, start: {"tenantId": tenant_id, "createdAt": {"$gte": start}},
    },
    "monthly_whatsapp_messages": {
        "collection": "whatsapp_message_logs",
        "filter": lambda tenant_id, start: {"tenantId": tenant_id, "direction": "outbound", "createdAt": {"$gte": start}},
    },
}


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def ensure_tenant_module_usage_available(tenant_id: ObjectId, module_code: str, increment: int = 1) -> None:
    """Enforce the plan usage cap for one module.

    This was a `return None` stub while five call sites awaited it as a guard, so every
    plan limit in the product was silently unenforced. Limits come from the module's
    own `usageLimits`, keyed by the tenant's plan, exactly as the seeds define them.

    A limit that cannot be counted, or a plan with no entry, means unlimited. Failing
    open is deliberate: refusing a legitimate action because a metric is unmapped would
    be worse than allowing an overage the owner can be billed for.
    """
    db = get_database()
    module = await db.modules.find_one({"code": module_code, "isActive": True})
    if not module:
        return

    tenant = await db.tenants.find_one({"_id": tenant_id})
    if not tenant:
        return

    # planCode is stored under tenant.settings, which is where tenant_service writes it
    # and where module_service, qa_service, onboarding_service and admin_service all read
    # it. Reading the top level made every tenant evaluate as "starter": paid tenants got
    # spurious 402s at the starter cap, and the AI modules, which declare no starter
    # entry, stayed unlimited for everyone.
    plan_code = str((tenant.get("settings") or {}).get("planCode") or tenant.get("planCode") or "starter")
    limits = (module.get("usageLimits") or {}).get(plan_code) or {}
    limit = limits.get("limit")
    if limit in (None, "") or float(limit) <= 0:
        return

    counter = _USAGE_COUNTERS.get(str(limits.get("metricCode") or ""))
    if not counter:
        return

    used = await db[counter["collection"]].count_documents(counter["filter"](tenant_id, _month_start()))
    if used + int(increment) > float(limit):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"This business has reached its {plan_code} plan limit for "
                f"{limits.get('label') or module_code} ({int(float(limit))}). Upgrade the plan to continue."
            ),
        )
