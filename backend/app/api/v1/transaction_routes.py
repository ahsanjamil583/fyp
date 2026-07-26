from fastapi import APIRouter, Depends, Query

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.transaction_schema import TransactionUpdateRequest
from app.services.transaction_service import list_transactions, update_transaction

router = APIRouter(prefix="/tenants/{tenantId}/transactions", tags=["transactions"])


@router.get("")
async def list_records(
    tenantId: str,
    search: str = "",
    status: str | None = Query(default=None),
    transactionType: str | None = Query(default=None),
    source: str | None = Query(default=None),
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_business_user),
):
    data = await list_transactions(tenantId, current_user, search, status, transactionType, source, page, limit)
    return success_response("Transactions fetched successfully.", data["items"], {**data["pagination"], "summary": data["summary"], "filters": data["filters"]})


@router.put("/{transactionId}")
async def update_record(
    tenantId: str,
    transactionId: str,
    payload: TransactionUpdateRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await update_transaction(tenantId, transactionId, payload, current_user)
    return success_response("Transaction updated successfully.", data)
