"""Order receipts and the settings that control confirmation messages.

The receipt route is public on purpose. A confirmation goes to guests who have no
account and may be read on a phone that has never signed in, so requiring a session
would make the link in the message useless to most of the people receiving it. The
token is the credential: 24 characters of URL-safe randomness, never derived from the
order id, and it grants nothing except that one receipt.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.core.object_ids import parse_object_id
from app.core.permissions import get_owned_tenant_or_403
from app.core.responses import success_response
from app.core.security import get_current_business_user, get_current_customer_user
from app.schemas.order_message_schema import OrderMessageSettingsRequest
from app.services.order_message_service import get_message_settings, update_message_settings
from app.services.order_receipt_service import (
    get_order_receipt_for_customer,
    get_order_receipt_html_by_token,
)

public_router = APIRouter(prefix="/receipts", tags=["order-receipts"])
customer_router = APIRouter(prefix="/customer", tags=["order-receipts"])
owner_router = APIRouter(prefix="/tenants/{tenantId}/order-messages", tags=["order-messages"])


@public_router.get("/{receiptToken}", response_class=HTMLResponse)
async def public_receipt(receiptToken: str):
    """Open a receipt from the link in a confirmation email or WhatsApp message."""
    html = await get_order_receipt_html_by_token(receiptToken)
    return HTMLResponse(content=html)


@customer_router.get("/transactions/{orderId}/receipt-link")
async def customer_receipt_link(orderId: str, current_user: dict = Depends(get_current_customer_user)):
    """The receipt token for an order the signed-in customer owns."""
    data = await get_order_receipt_for_customer(orderId, current_user)
    return success_response("Receipt link fetched successfully.", data)


@owner_router.get("")
async def read_settings(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    tenant_oid = parse_object_id(tenantId, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, current_user)
    data = await get_message_settings(tenant_oid)
    return success_response("Order message settings fetched successfully.", data)


@owner_router.put("")
async def write_settings(
    tenantId: str,
    payload: OrderMessageSettingsRequest,
    current_user: dict = Depends(get_current_business_user),
):
    tenant_oid = parse_object_id(tenantId, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, current_user)
    data = await update_message_settings(tenant_oid, payload)
    return success_response("Order message settings updated successfully.", data)
