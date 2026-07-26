from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.services.business_notification_service import (
    list_business_notifications,
    mark_all_business_notifications_read,
    mark_business_notification_read,
    sync_low_stock_notifications,
)

router = APIRouter(prefix="/tenants/{tenantId}/notifications", tags=["business-notifications"])


@router.get("")
async def list_notifications(
    tenantId: str,
    page: int = 1,
    limit: int = 20,
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    current_user: dict = Depends(get_current_business_user),
):
    data = await list_business_notifications(tenantId, current_user, page=page, limit=limit, notification_type=type, status_filter=status)
    return success_response("Business notifications fetched successfully.", data["items"], {**data["pagination"], "filters": data["filters"]})


@router.post("/{notificationId}/read")
async def mark_read(tenantId: str, notificationId: str, current_user: dict = Depends(get_current_business_user)):
    data = await mark_business_notification_read(tenantId, notificationId, current_user)
    return success_response("Business notification updated successfully.", data)


@router.post("/read-all")
async def mark_all_read(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await mark_all_business_notifications_read(tenantId, current_user)
    return success_response("Business notifications marked as read.", data)


@router.post("/refresh-stock-alerts")
async def refresh_stock_alerts(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    from app.core.object_ids import parse_object_id
    from app.core.permissions import get_owned_tenant_or_403

    tenant_oid = parse_object_id(tenantId, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, current_user)
    data = await sync_low_stock_notifications(tenant_oid)
    return success_response("Stock alerts refreshed successfully.", data)
