from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.services.reporting_service import generate_daily_summary, get_daily_summary

router = APIRouter(prefix="/tenants/{tenantId}/reports", tags=["reports"])


@router.get("/daily-summary")
async def daily_summary(
    tenantId: str,
    date: str | None = Query(default=None),
    current_user: dict = Depends(get_current_business_user),
):
    data = await get_daily_summary(tenantId, current_user, date)
    return success_response("Daily summary fetched successfully.", data)


@router.post("/daily-summary/generate")
async def generate_summary(
    tenantId: str,
    date: str | None = Query(default=None),
    current_user: dict = Depends(get_current_business_user),
):
    data = await generate_daily_summary(tenantId, current_user, date)
    return success_response("Daily summary generated successfully.", data)
