from fastapi import APIRouter, Query

from app.core.responses import success_response
from app.schemas.public_chat_schema import PublicChatMessageRequest
from app.schemas.public_website_schema import PublicOrderRequest
from app.services.ai_chat_service import get_public_chat_state, send_public_chat_message
from app.services.public_website_service import create_public_order, create_public_transaction, get_public_business, get_public_item, list_public_items
from app.schemas.payment_schema import StripeCheckoutSessionRequest, StripePaymentSyncRequest
from app.services.payment_service import create_public_stripe_checkout_session, sync_public_stripe_checkout_session

router = APIRouter(prefix="/public/businesses", tags=["public-website"])


@router.get("/{tenantSlug}")
async def business(tenantSlug: str):
    data = await get_public_business(tenantSlug)
    return success_response("Published business fetched successfully.", data)


@router.get("/{tenantSlug}/items")
async def items(
    tenantSlug: str,
    search: str = "",
    itemType: str | None = Query(default=None),
    page: int = 1,
    limit: int = 20,
):
    data = await list_public_items(tenantSlug, search, itemType, page, limit)
    return success_response("Public items fetched successfully.", data["items"], data["pagination"])


@router.get("/{tenantSlug}/items/{itemId}")
async def item_detail(tenantSlug: str, itemId: str):
    data = await get_public_item(tenantSlug, itemId)
    return success_response("Public item fetched successfully.", data)


@router.get("/{tenantSlug}/chat")
async def chat_state(tenantSlug: str, conversationId: str | None = Query(default=None)):
    data = await get_public_chat_state(tenantSlug, conversationId)
    return success_response("Public AI chat fetched successfully.", data)


@router.post("/{tenantSlug}/chat/messages")
async def chat_message(tenantSlug: str, payload: PublicChatMessageRequest):
    data = await send_public_chat_message(tenantSlug, payload.messageText, payload.conversationId)
    return success_response("Public AI chat message processed successfully.", data)


@router.post("/{tenantSlug}/transactions")
async def transaction(tenantSlug: str, payload: PublicOrderRequest):
    data = await create_public_transaction(tenantSlug, payload)
    return success_response("Transaction created successfully.", data)


@router.post("/{tenantSlug}/orders")
async def order(tenantSlug: str, payload: PublicOrderRequest):
    data = await create_public_order(tenantSlug, payload)
    return success_response("Transaction created successfully.", data)


@router.post("/{tenantSlug}/transactions/{transactionId}/stripe-checkout")
async def public_stripe_checkout(tenantSlug: str, transactionId: str, payload: StripeCheckoutSessionRequest):
    data = await create_public_stripe_checkout_session(tenantSlug, transactionId, payload.successUrl, payload.cancelUrl)
    return success_response("Stripe checkout session created successfully.", data)


@router.post("/{tenantSlug}/transactions/{transactionId}/stripe-checkout/sync")
async def public_stripe_checkout_sync(tenantSlug: str, transactionId: str, payload: StripePaymentSyncRequest):
    data = await sync_public_stripe_checkout_session(tenantSlug, transactionId, payload.sessionId)
    return success_response("Stripe checkout synced successfully.", data)
