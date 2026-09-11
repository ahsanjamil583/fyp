from fastapi import APIRouter, Depends

from app.core.permissions import require_platform_admin
from app.core.responses import success_response
from app.core.security import get_current_user
from app.schemas.admin_schema import (
    AdminModuleUpdateRequest,
    AdminPackageUpgradeDecisionRequest,
    AdminTenantUpdateRequest,
    AdminUserUpdateRequest,
    AdminWebsiteRequestDecisionRequest,
)
from app.schemas.module_schema import ModuleCreateRequest
from app.services.admin_service import (
    decide_admin_package_upgrade,
    decide_admin_website_request,
    get_admin_overview,
    get_admin_payments,
    get_admin_reports,
    list_admin_modules,
    list_admin_tenants,
    list_admin_users,
    update_admin_module,
    update_admin_tenant,
    update_admin_user,
)
from app.services.module_service import create_module

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
async def overview(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await get_admin_overview()
    return success_response("Admin overview fetched successfully.", data)


@router.get("/reports")
async def reports(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await get_admin_reports()
    return success_response("Admin reports fetched successfully.", data)


@router.get("/payments")
async def payments(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await get_admin_payments()
    return success_response("Admin payments fetched successfully.", data)


@router.get("/users")
async def users(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await list_admin_users()
    return success_response("Admin users fetched successfully.", data)


@router.put("/users/{userId}")
async def update_user(userId: str, payload: AdminUserUpdateRequest, current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await update_admin_user(userId, payload, current_user)
    return success_response("Admin user updated successfully.", data)


@router.get("/tenants")
async def tenants(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await list_admin_tenants()
    return success_response("Admin tenants fetched successfully.", data)


@router.put("/tenants/{tenantId}")
async def update_tenant(tenantId: str, payload: AdminTenantUpdateRequest, current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await update_admin_tenant(tenantId, payload)
    return success_response("Admin tenant updated successfully.", data)


@router.post("/tenants/{tenantId}/package-requests/{planCode}/decision")
async def decide_package_request(
    tenantId: str,
    planCode: str,
    payload: AdminPackageUpgradeDecisionRequest,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)
    data = await decide_admin_package_upgrade(tenantId, planCode, payload, current_user)
    return success_response("Package upgrade request updated successfully.", data)


@router.post("/tenants/{tenantId}/website-request/decision")
async def decide_website_request(
    tenantId: str,
    payload: AdminWebsiteRequestDecisionRequest,
    current_user: dict = Depends(get_current_user),
):
    require_platform_admin(current_user)
    data = await decide_admin_website_request(tenantId, payload, current_user)
    return success_response("Website request updated successfully.", data)


@router.get("/modules")
async def modules(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await list_admin_modules()
    return success_response("Admin modules fetched successfully.", data)


@router.post("/modules")
async def create_admin_module(payload: ModuleCreateRequest, current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await create_module(payload)
    return success_response("Admin module created successfully.", data)


@router.put("/modules/{moduleCode}")
async def update_module(moduleCode: str, payload: AdminModuleUpdateRequest, current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await update_admin_module(moduleCode, payload)
    return success_response("Admin module updated successfully.", data)
