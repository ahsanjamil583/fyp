from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.module_schema import TenantModuleConfigRequest
from app.services.module_service import disable_tenant_module, enable_tenant_module, list_modules, list_tenant_modules, update_tenant_module_config

router = APIRouter(tags=["modules"])


@router.get("/modules")
async def modules():
    data = await list_modules()
    return success_response("Modules fetched successfully.", data)


@router.get("/tenants/{tenantId}/modules")
async def tenant_modules(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await list_tenant_modules(tenantId, current_user)
    return success_response("Tenant modules fetched successfully.", data)


@router.post("/tenants/{tenantId}/modules/{moduleCode}/enable")
async def enable_module(tenantId: str, moduleCode: str, current_user: dict = Depends(get_current_business_user)):
    data = await enable_tenant_module(tenantId, moduleCode, current_user)
    return success_response("Module enabled successfully.", data)


@router.post("/tenants/{tenantId}/modules/{moduleCode}/disable")
async def disable_module(tenantId: str, moduleCode: str, current_user: dict = Depends(get_current_business_user)):
    data = await disable_tenant_module(tenantId, moduleCode, current_user)
    return success_response("Module disabled successfully.", data)


@router.put("/tenants/{tenantId}/modules/{moduleCode}/config")
async def update_module_config(
    tenantId: str,
    moduleCode: str,
    payload: TenantModuleConfigRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await update_tenant_module_config(tenantId, moduleCode, payload, current_user)
    return success_response("Module config updated successfully.", data)
