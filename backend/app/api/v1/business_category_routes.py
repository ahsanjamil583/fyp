from fastapi import APIRouter, Depends

from app.core.permissions import require_platform_admin
from app.core.responses import success_response
from app.core.security import get_current_user
from app.schemas.business_category_schema import BusinessCategoryCreateRequest, BusinessCategoryUpdateRequest
from app.services.business_category_service import create_category, delete_category, list_admin_categories, list_public_categories, update_category

router = APIRouter(tags=["business-categories"])


@router.get("/public/business-categories")
async def public_categories():
    data = await list_public_categories()
    return success_response("Business categories fetched successfully.", data)


@router.get("/admin/business-categories")
async def admin_categories(current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await list_admin_categories()
    return success_response("Admin business categories fetched successfully.", data)


@router.post("/admin/business-categories")
async def admin_create_category(payload: BusinessCategoryCreateRequest, current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await create_category(payload)
    return success_response("Business category created successfully.", data)


@router.put("/admin/business-categories/{categoryId}")
async def admin_update_category(categoryId: str, payload: BusinessCategoryUpdateRequest, current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await update_category(categoryId, payload)
    return success_response("Business category updated successfully.", data)


@router.delete("/admin/business-categories/{categoryId}")
async def admin_delete_category(categoryId: str, current_user: dict = Depends(get_current_user)):
    require_platform_admin(current_user)
    data = await delete_category(categoryId)
    return success_response("Business category disabled successfully.", data)
