"""Owner-side import of historical order sheets."""

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.cashier_schema import OrderImportConfirmRequest
from app.services.order_import_service import (
    confirm_order_import,
    get_order_import_error_report,
    import_column_guide,
    list_order_imports,
    preview_order_sheet,
)

router = APIRouter(prefix="/tenants/{tenantId}/transactions/imports", tags=["order-imports"])


@router.get("/columns")
async def columns(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    return success_response("Expected import columns fetched successfully.", import_column_guide())


@router.post("/preview")
async def preview(tenantId: str, file: UploadFile = File(...), current_user: dict = Depends(get_current_business_user)):
    data = await preview_order_sheet(tenantId, file, current_user)
    return success_response("Order sheet parsed successfully.", data)


@router.post("/confirm")
async def confirm(tenantId: str, payload: OrderImportConfirmRequest, current_user: dict = Depends(get_current_business_user)):
    data = await confirm_order_import(tenantId, payload, current_user)
    return success_response("Order import completed.", data)


@router.get("")
async def history(tenantId: str, page: int = 1, limit: int = 20, current_user: dict = Depends(get_current_business_user)):
    data = await list_order_imports(tenantId, current_user, page, limit)
    return success_response("Import history fetched successfully.", data["items"], data["pagination"])


@router.get("/{importId}/errors.csv")
async def error_report(tenantId: str, importId: str, current_user: dict = Depends(get_current_business_user)):
    filename, csv_text = await get_order_import_error_report(tenantId, importId, current_user)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
