from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.onboarding_schema import LaunchFinalizeRequest, LaunchProfileRequest
from app.services.onboarding_service import apply_launch_profile, finalize_launch, get_launch_status, request_package_upgrade

router = APIRouter(tags=["onboarding"])


@router.get("/tenants/{tenantId}/launch/status")
async def launch_status(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_launch_status(tenantId, current_user)
    return success_response("Launch status fetched successfully.", data)


@router.post("/tenants/{tenantId}/launch/apply-profile")
async def launch_apply_profile(
    tenantId: str,
    payload: LaunchProfileRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await apply_launch_profile(tenantId, payload, current_user)
    return success_response("Launch profile applied successfully.", data)


@router.post("/tenants/{tenantId}/launch/request-upgrade")
async def launch_request_upgrade(
    tenantId: str,
    payload: LaunchProfileRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await request_package_upgrade(tenantId, payload, current_user)
    return success_response("Package upgrade requested successfully.", data)


@router.post("/tenants/{tenantId}/launch/finalize")
async def launch_finalize(
    tenantId: str,
    payload: LaunchFinalizeRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await finalize_launch(tenantId, payload, current_user)
    return success_response("Launch finalized successfully.", data)
