from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.tenant_schema import TenantCreateRequest, TenantUpdateRequest
from app.services.tenant_service import create_tenant, get_tenant, list_my_tenants, publish_tenant, unpublish_tenant, update_tenant

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("")
async def create(payload: TenantCreateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await create_tenant(payload, current_user)
    return success_response("Tenant created successfully.", data)


@router.get("/my")
async def my_tenants(current_user: dict = Depends(get_current_business_user)):
    data = await list_my_tenants(current_user)
    return success_response("Tenants fetched successfully.", data)


@router.get("/{tenantId}")
async def detail(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_tenant(tenantId, current_user)
    return success_response("Tenant fetched successfully.", data)


@router.put("/{tenantId}")
async def update(tenantId: str, payload: TenantUpdateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await update_tenant(tenantId, payload, current_user)
    return success_response("Tenant updated successfully.", data)


@router.post("/{tenantId}/publish")
async def publish(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await publish_tenant(tenantId, current_user)
    return success_response("Tenant published successfully.", data)


@router.post("/{tenantId}/unpublish")
async def unpublish(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await unpublish_tenant(tenantId, current_user)
    return success_response("Tenant unpublished successfully.", data)
