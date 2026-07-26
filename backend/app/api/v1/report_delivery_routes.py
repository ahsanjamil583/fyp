from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.report_delivery_schema import ReportDeliveryRequest, ReportDeliverySettingsRequest, ScheduledReportRunRequest
from app.services.report_delivery_service import (
    deliver_daily_summary,
    get_report_delivery_settings,
    list_report_delivery_logs,
    run_scheduled_report_delivery,
    update_report_delivery_settings,
)

router = APIRouter(prefix="/tenants/{tenantId}/reports/delivery", tags=["report-delivery"])


@router.get("/settings")
async def settings(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_report_delivery_settings(tenantId, current_user)
    return success_response("Daily report delivery settings fetched successfully.", data)


@router.put("/settings")
async def update_settings(
    tenantId: str,
    payload: ReportDeliverySettingsRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await update_report_delivery_settings(tenantId, payload, current_user)
    return success_response("Daily report delivery settings updated successfully.", data)


@router.post("/daily-summary")
async def deliver(
    tenantId: str,
    payload: ReportDeliveryRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await deliver_daily_summary(tenantId, payload, current_user)
    return success_response("Daily report delivery completed.", data)


@router.post("/run-scheduled")
async def run_scheduled(
    tenantId: str,
    payload: ScheduledReportRunRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await run_scheduled_report_delivery(tenantId, payload, current_user)
    return success_response("Scheduled daily report delivery checked successfully.", data)


@router.get("/logs")
async def logs(
    tenantId: str,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_business_user),
):
    data = await list_report_delivery_logs(tenantId, current_user, limit=limit)
    return success_response("Daily report delivery logs fetched successfully.", data["items"], {"tenant": data["tenant"]})
