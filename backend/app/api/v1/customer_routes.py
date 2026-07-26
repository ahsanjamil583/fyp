from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.customer_schema import CustomerCreateRequest, CustomerUpdateRequest
from app.services.customer_service import create_customer, delete_customer, get_customer, get_customer_insights, list_customers, update_customer

router = APIRouter(prefix="/tenants/{tenantId}/customers", tags=["customers"])


@router.post("")
async def create(tenantId: str, payload: CustomerCreateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await create_customer(tenantId, payload, current_user)
    return success_response("Customer created successfully.", data)


@router.get("")
async def list_records(
    tenantId: str,
    search: str = "",
    status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    segment: str | None = Query(default=None),
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_business_user),
):
    data = await list_customers(tenantId, current_user, search, status, tag, segment, page, limit)
    return success_response("Customers fetched successfully.", data["items"], {**data["pagination"], "filters": data["filters"], "insights": data["insights"]})


@router.get("/insights")
async def insights(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_customer_insights(tenantId, current_user)
    return success_response("Customer insights fetched successfully.", data)


@router.get("/{customerId}")
async def detail(tenantId: str, customerId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_customer(tenantId, customerId, current_user)
    return success_response("Customer fetched successfully.", data)


@router.put("/{customerId}")
async def update(tenantId: str, customerId: str, payload: CustomerUpdateRequest, current_user: dict = Depends(get_current_business_user)):
    data = await update_customer(tenantId, customerId, payload, current_user)
    return success_response("Customer updated successfully.", data)


@router.delete("/{customerId}")
async def delete(tenantId: str, customerId: str, current_user: dict = Depends(get_current_business_user)):
    data = await delete_customer(tenantId, customerId, current_user)
    return success_response("Customer deleted successfully.", data)
