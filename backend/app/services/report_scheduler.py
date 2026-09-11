import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.db.mongodb import get_database
from app.schemas.report_delivery_schema import ScheduledReportRunRequest
from app.services.report_delivery_service import run_scheduled_report_delivery

logger = logging.getLogger(__name__)


def report_is_due(config: dict, now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(config.get("timezone") or "Asia/Karachi"))
    return bool(config.get("enabled") and local.strftime("%H:%M") >= config.get("deliveryTime", "21:00"))


async def run_due_reports():
    db = get_database()
    now = datetime.now(timezone.utc)
    async for config in db.report_delivery_settings.find({"enabled": True}):
        try:
            if not report_is_due(config, now):
                continue
            tenant = await db.tenants.find_one({"_id": config["tenantId"], "status": "active"})
            if not tenant:
                continue
            owner = await db.users.find_one({"_id": tenant.get("ownerUserId"), "status": "active"})
            if not owner or owner.get("mustResetPassword"):
                continue
            date_key = now.astimezone(ZoneInfo(config.get("timezone") or "Asia/Karachi")).strftime("%Y-%m-%d")
            await run_scheduled_report_delivery(str(tenant["_id"]), ScheduledReportRunRequest(summaryDate=date_key, dryRun=False), owner)
        except Exception:
            logger.exception("Scheduled report failed for tenant %s", config.get("tenantId"))


async def report_scheduler_loop():
    while True:
        try:
            await run_due_reports()
        except Exception:
            logger.exception("Report scheduler iteration failed")
        await asyncio.sleep(60)
