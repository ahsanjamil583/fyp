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


async def ensure_tenant_module_usage_available(tenant_id: ObjectId, module_code: str, increment: int = 1) -> None:
    return None
