from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.item_schema import ItemCategoryCreateRequest, ItemCategoryUpdateRequest, ItemCreateRequest, ItemUpdateRequest
from app.services.item_service import (
    create_item,
    create_item_category,
    delete_item,
    delete_item_category,
    get_item,
    import_items_from_excel,
    list_item_categories,
    list_items,
    update_item,
    update_item_category,
    upload_item_image,
)

router = APIRouter(prefix="/tenants/{tenantId}", tags=["items"])


@router.post("/item-categories")
async def create_category(tenantId: str, payload: ItemCategoryCreateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await create_item_category(tenantId, payload, current_user)
    return success_response("Item category created successfully.", data)


@router.get("/item-categories")
async def categories(tenantId: str, activeOnly: bool = False, current_user: dict = Depends(get_current_business_user)):
    data = await list_item_categories(tenantId, current_user, activeOnly)
    return success_response("Item categories fetched successfully.", data)


@router.put("/item-categories/{categoryId}")
async def update_category(tenantId: str, categoryId: str, payload: ItemCategoryUpdateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await update_item_category(tenantId, categoryId, payload, current_user)
    return success_response("Item category updated successfully.", data)


@router.delete("/item-categories/{categoryId}")
async def delete_category(tenantId: str, categoryId: str, current_user: dict = Depends(get_current_business_user)):
    data = await delete_item_category(tenantId, categoryId, current_user)
    return success_response("Item category disabled successfully.", data)


@router.post("/items")
async def create(tenantId: str, payload: ItemCreateRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_business_user)):
    data = await create_item(tenantId, payload, current_user, background_tasks)
    return success_response("Item created successfully.", data)


@router.get("/items")
async def list_records(
    tenantId: str,
    search: str = "",
    status: str | None = Query(default=None),
    itemType: str | None = Query(default=None),
    categoryId: str | None = Query(default=None),
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_business_user),
):
    data = await list_items(tenantId, current_user, search, status, itemType, categoryId, page, limit)
    return success_response("Items fetched successfully.", data["items"], data["pagination"])


@router.get("/items/{itemId}")
async def detail(tenantId: str, itemId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_item(tenantId, itemId, current_user)
    return success_response("Item fetched successfully.", data)


@router.put("/items/{itemId}")
async def update(tenantId: str, itemId: str, payload: ItemUpdateRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_business_user)):
    data = await update_item(tenantId, itemId, payload, current_user, background_tasks)
    return success_response("Item updated successfully.", data)


@router.delete("/items/{itemId}")
async def delete(tenantId: str, itemId: str, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_business_user)):
    data = await delete_item(tenantId, itemId, current_user, background_tasks)
    return success_response("Item archived successfully.", data)


@router.post("/items/{itemId}/images")
async def upload_image(
    tenantId: str,
    itemId: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_business_user),
):
    data = await upload_item_image(tenantId, itemId, file, current_user, background_tasks)
    return success_response("Item image uploaded successfully.", data)


@router.post("/items/import")
async def import_items(
    tenantId: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_business_user),
):
    data = await import_items_from_excel(tenantId, file, current_user, background_tasks)
    return success_response("Item import completed.", data)
