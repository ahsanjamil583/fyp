from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.custom_field_schema import CustomFieldCreateRequest, CustomFieldUpdateRequest, CustomValuesValidationRequest
from app.services.custom_field_service import create_custom_field, delete_custom_field, list_custom_fields, update_custom_field, validate_custom_values

router = APIRouter(prefix="/tenants/{tenantId}/custom-fields", tags=["custom-fields"])


@router.post("")
async def create(tenantId: str, payload: CustomFieldCreateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await create_custom_field(tenantId, payload, current_user)
    return success_response("Custom field created successfully.", data)


@router.get("")
async def list_fields(
    tenantId: str,
    moduleCode: str | None = Query(default=None),
    entityType: str | None = Query(default=None),
    current_user: dict = Depends(get_current_business_user),
):
    data = await list_custom_fields(tenantId, current_user, moduleCode, entityType)
    return success_response("Custom fields fetched successfully.", data)


@router.put("/{fieldId}")
async def update(tenantId: str, fieldId: str, payload: CustomFieldUpdateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await update_custom_field(tenantId, fieldId, payload, current_user)
    return success_response("Custom field updated successfully.", data)


@router.delete("/{fieldId}")
async def delete(tenantId: str, fieldId: str, current_user: dict = Depends(get_current_business_user)):
    data = await delete_custom_field(tenantId, fieldId, current_user)
    return success_response("Custom field disabled successfully.", data)


@router.post("/validate-values")
async def validate_values(tenantId: str, payload: CustomValuesValidationRequest, current_user: dict = Depends(get_current_business_user)):
    data = await validate_custom_values(tenantId, payload.moduleCode, payload.entityType, payload.values, current_user)
    return success_response("Custom values validated successfully.", data)
