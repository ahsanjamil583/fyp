from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.services.analytics_service import get_analytics_summary

router = APIRouter(prefix="/tenants/{tenantId}/analytics", tags=["analytics"])


@router.get("/summary")
async def analytics_summary(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_analytics_summary(tenantId, current_user)
    return success_response("Analytics summary fetched successfully.", data)
