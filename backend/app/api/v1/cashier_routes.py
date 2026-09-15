"""Cashier module endpoints.

Two routers with deliberately different guards:

* ``owner_router`` - ``/tenants/{tenantId}/cashiers``, depends on the business-owner
  dependency and on tenant ownership, so one owner can never manage another's staff.
* ``cashier_router`` - ``/cashier/...``, depends on the cashier dependency. None of these
  routes takes a tenant id from the request: the tenant comes from the account, which is
  what makes cross-tenant access impossible rather than merely discouraged.
"""

from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.core.security import get_current_business_user, get_current_cashier_user
from app.schemas.cashier_schema import (
    CashierCreateRequest,
    CashierOrderCreateRequest,
    CashierPasswordResetRequest,
    CashierStatusRequest,
    CashierUpdateRequest,
)
from app.services.cashier_order_service import (
    create_cashier_order,
    get_cashier_dashboard,
    get_cashier_order,
    get_cashier_receipt,
    list_cashier_catalog,
    list_cashier_orders,
)
from app.services.cashier_service import (
    cashier_public,
    create_cashier,
    delete_cashier,
    get_cashier,
    get_cashier_context,
    list_cashiers,
    reset_cashier_password,
    set_cashier_status,
    update_cashier,
)

owner_router = APIRouter(prefix="/tenants/{tenantId}/cashiers", tags=["cashiers"])
cashier_router = APIRouter(prefix="/cashier", tags=["cashier-workspace"])


# --------------------------------------------------------------- owner side --


@owner_router.get("")
async def list_records(
    tenantId: str,
    activeOnly: bool | None = Query(default=None),
    current_user: dict = Depends(get_current_business_user),
):
    data = await list_cashiers(tenantId, current_user, activeOnly)
    return success_response("Cashiers fetched successfully.", data["items"], {"summary": data["summary"]})


@owner_router.post("")
async def create_record(tenantId: str, payload: CashierCreateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await create_cashier(tenantId, payload, current_user)
    return success_response("Cashier created successfully.", data)


@owner_router.get("/{cashierId}")
async def detail(tenantId: str, cashierId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_cashier(tenantId, cashierId, current_user)
    return success_response("Cashier fetched successfully.", data)


@owner_router.put("/{cashierId}")
async def update_record(tenantId: str, cashierId: str, payload: CashierUpdateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await update_cashier(tenantId, cashierId, payload, current_user)
    return success_response("Cashier updated successfully.", data)


@owner_router.post("/{cashierId}/status")
async def change_status(tenantId: str, cashierId: str, payload: CashierStatusRequest, current_user: dict = Depends(get_current_business_user)):
    data = await set_cashier_status(tenantId, cashierId, payload, current_user)
    return success_response("Cashier status updated successfully.", data)


@owner_router.post("/{cashierId}/password")
async def reset_password(tenantId: str, cashierId: str, payload: CashierPasswordResetRequest, current_user: dict = Depends(get_current_business_user)):
    data = await reset_cashier_password(tenantId, cashierId, payload, current_user)
    return success_response("Cashier password reset successfully.", data)


@owner_router.delete("/{cashierId}")
async def remove_record(tenantId: str, cashierId: str, current_user: dict = Depends(get_current_business_user)):
    data = await delete_cashier(tenantId, cashierId, current_user)
    return success_response("Cashier access removed successfully.", data)


# ------------------------------------------------------------- cashier side --


@cashier_router.get("/me")
async def me(current_user: dict = Depends(get_current_cashier_user)):
    cashier, tenant = await get_cashier_context(current_user)
    data = cashier_public(cashier, current_user)
    data["business"] = {
        "name": tenant.get("name", ""),
        "slug": tenant.get("slug", ""),
        "currency": ((tenant.get("settings") or {}).get("currency")) or "PKR",
        "logoUrl": (tenant.get("logo") or {}).get("url", ""),
    }
    return success_response("Cashier profile fetched successfully.", data)


@cashier_router.get("/dashboard")
async def dashboard(current_user: dict = Depends(get_current_cashier_user)):
    data = await get_cashier_dashboard(current_user)
    return success_response("Cashier dashboard fetched successfully.", data)


@cashier_router.get("/catalog")
async def catalog(search: str = "", limit: int = 40, current_user: dict = Depends(get_current_cashier_user)):
    data = await list_cashier_catalog(current_user, search, limit)
    return success_response("Catalog fetched successfully.", data)


@cashier_router.get("/orders")
async def orders(
    search: str = "",
    status: str | None = Query(default=None),
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_cashier_user),
):
    data = await list_cashier_orders(current_user, search, status, page, limit)
    return success_response("Cashier orders fetched successfully.", data["items"], data["pagination"])


@cashier_router.post("/orders")
async def create_order(payload: CashierOrderCreateRequest, current_user: dict = Depends(get_current_cashier_user)):
    data = await create_cashier_order(current_user, payload)
    return success_response("Order created successfully.", data)


@cashier_router.get("/orders/{receiptToken}")
async def order_detail(receiptToken: str, current_user: dict = Depends(get_current_cashier_user)):
    data = await get_cashier_order(current_user, receiptToken)
    return success_response("Order fetched successfully.", data)


@cashier_router.get("/receipts/{receiptToken}")
async def receipt(receiptToken: str, current_user: dict = Depends(get_current_cashier_user)):
    data = await get_cashier_receipt(current_user, receiptToken)
    return success_response("Receipt fetched successfully.", data)
