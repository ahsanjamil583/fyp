from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import HTMLResponse

from app.core.responses import success_response
from app.core.private_uploads import customer_payment_result
from app.core.security import get_current_customer_user
from app.schemas.customer_portal_schema import CartItemCreateRequest, CartItemUpdateRequest, CustomerChatMessageRequest, CustomerDraftConfirmRequest, CustomerOrderCreateRequest, FavoriteItemRequest
from app.services.customer_notification_service import list_customer_notifications, mark_all_customer_notifications_read, mark_customer_notification_read
from app.services.ai_chat_service import get_customer_chat_state, send_customer_chat_message
from app.services.customer_portal_service import (
    add_cart_item,
    add_customer_favorite,
    confirm_customer_draft_order,
    create_customer_order,
    create_customer_transaction,
    get_customer_cart,
    get_customer_order,
    get_customer_transaction,
    list_customer_favorites,
    get_marketplace_business,
    get_marketplace_item,
    list_customer_orders,
    list_customer_transactions,
    list_marketplace_businesses,
    list_marketplace_catalog,
    list_marketplace_items,
    remove_customer_favorite,
    reorder_customer_transaction,
    remove_cart_item,
    update_cart_item,
)
from app.services.payment_service import submit_customer_payment_proof
from app.services.payment_service import create_customer_stripe_checkout_session, create_gateway_checkout, get_customer_payment_receipt_html, sync_customer_stripe_checkout_session
from app.schemas.payment_schema import GatewayCheckoutRequest, StripeCheckoutSessionRequest, StripePaymentSyncRequest

router = APIRouter(prefix="/customer", tags=["customer-portal"])


@router.get("/marketplace")
async def marketplace(
    search: str = "",
    city: str = "",
    categoryId: str | None = Query(default=None),
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_customer_user),
):
    data = await list_marketplace_businesses(search, city, categoryId, page, limit)
    return success_response("Marketplace businesses fetched successfully.", data["items"], data["pagination"])


@router.get("/marketplace/items")
async def marketplace_catalog(
    search: str = "",
    itemType: str | None = None,
    city: str = "",
    businessCategoryId: str | None = None,
    category: str = "",
    page: int = 1,
    limit: int = 24,
    current_user: dict = Depends(get_current_customer_user),
):
    """Products and services from every published business, for category-first browsing."""
    data = await list_marketplace_catalog(
        search=search,
        item_type=itemType,
        city=city,
        business_category_id=businessCategoryId,
        category=category,
        page=page,
        limit=limit,
    )
    return success_response("Marketplace catalog fetched successfully.", data)


@router.get("/businesses/{tenantSlug}")
async def business(tenantSlug: str, current_user: dict = Depends(get_current_customer_user)):
    data = await get_marketplace_business(tenantSlug)
    return success_response("Marketplace business fetched successfully.", data)


@router.get("/businesses/{tenantSlug}/items")
async def items(
    tenantSlug: str,
    search: str = "",
    itemType: str | None = Query(default=None),
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_customer_user),
):
    data = await list_marketplace_items(tenantSlug, search, itemType, page, limit)
    return success_response("Marketplace items fetched successfully.", data["items"], data["pagination"])


@router.get("/businesses/{tenantSlug}/items/{itemId}")
async def item_detail(tenantSlug: str, itemId: str, current_user: dict = Depends(get_current_customer_user)):
    data = await get_marketplace_item(tenantSlug, itemId)
    return success_response("Marketplace item fetched successfully.", data)


@router.get("/businesses/{tenantSlug}/chat")
async def chat_state(tenantSlug: str, current_user: dict = Depends(get_current_customer_user)):
    data = await get_customer_chat_state(tenantSlug, current_user)
    return success_response("Customer chat fetched successfully.", data)


@router.post("/businesses/{tenantSlug}/chat/messages")
async def chat_message(tenantSlug: str, payload: CustomerChatMessageRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await send_customer_chat_message(tenantSlug, payload.messageText, current_user)
    return success_response("Customer chat message processed successfully.", data)


@router.get("/cart")
async def cart(current_user: dict = Depends(get_current_customer_user)):
    data = await get_customer_cart(current_user)
    return success_response("Customer cart fetched successfully.", data)


@router.get("/favorites")
async def favorites(current_user: dict = Depends(get_current_customer_user)):
    data = await list_customer_favorites(current_user)
    return success_response("Customer favorites fetched successfully.", data)


@router.post("/favorites/items")
async def add_favorite(payload: FavoriteItemRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await add_customer_favorite(payload, current_user)
    return success_response("Favorite added successfully.", data)


@router.delete("/favorites/items/{itemId}")
async def remove_favorite(itemId: str, tenantId: str, current_user: dict = Depends(get_current_customer_user)):
    data = await remove_customer_favorite(itemId, tenantId, current_user)
    return success_response("Favorite removed successfully.", data)


@router.post("/cart/items")
async def add_item(payload: CartItemCreateRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await add_cart_item(payload, current_user)
    return success_response("Item added to cart successfully.", data)


@router.put("/cart/items/{itemId}")
async def update_item(itemId: str, payload: CartItemUpdateRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await update_cart_item(itemId, payload, current_user)
    return success_response("Cart item updated successfully.", data)


@router.delete("/cart/items/{itemId}")
async def remove_item(itemId: str, current_user: dict = Depends(get_current_customer_user)):
    data = await remove_cart_item(itemId, current_user)
    return success_response("Cart item removed successfully.", data)


@router.post("/transactions")
async def create_transaction(payload: CustomerOrderCreateRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await create_customer_transaction(payload, current_user)
    return success_response("Customer transaction created successfully.", data)


@router.post("/orders")
async def create_order(payload: CustomerOrderCreateRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await create_customer_order(payload, current_user)
    return success_response("Customer transaction created successfully.", data)


@router.post("/businesses/{tenantSlug}/orders/confirm-draft")
async def confirm_draft(tenantSlug: str, payload: CustomerDraftConfirmRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await confirm_customer_draft_order(tenantSlug, payload, current_user)
    return success_response("Draft transaction confirmed successfully.", data)


@router.get("/transactions")
async def transactions(page: int = 1, limit: int = 20, current_user: dict = Depends(get_current_customer_user)):
    data = await list_customer_transactions(current_user, page, limit)
    return success_response("Customer transactions fetched successfully.", data["items"], data["pagination"])


@router.get("/orders")
async def orders(page: int = 1, limit: int = 20, current_user: dict = Depends(get_current_customer_user)):
    data = await list_customer_orders(current_user, page, limit)
    return success_response("Customer transactions fetched successfully.", data["items"], data["pagination"])


@router.post("/transactions/{orderId}/payment-proof")
async def submit_payment_proof(
    orderId: str,
    amount: float = Form(...),
    method: str = Form(default=""),
    referenceNumber: str = Form(default=""),
    notes: str = Form(default=""),
    proofFile: UploadFile | None = File(default=None),
    current_user: dict = Depends(get_current_customer_user),
):
    data = await submit_customer_payment_proof(orderId, amount, method, referenceNumber, notes, current_user, proofFile)
    return success_response("Payment proof submitted successfully.", customer_payment_result(data))


@router.post("/transactions/{orderId}/gateway-checkout")
async def start_gateway_checkout(orderId: str, payload: GatewayCheckoutRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await create_gateway_checkout(orderId, payload.provider.strip().lower(), current_user)
    return success_response(f"{data['label']} checkout started successfully.", customer_payment_result(data))


@router.post("/transactions/{orderId}/stripe-checkout")
async def create_stripe_checkout(orderId: str, payload: StripeCheckoutSessionRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await create_customer_stripe_checkout_session(orderId, current_user, payload.successUrl, payload.cancelUrl)
    return success_response("Stripe checkout session created successfully.", customer_payment_result(data))


@router.post("/transactions/{orderId}/stripe-checkout/sync")
async def sync_stripe_checkout(orderId: str, payload: StripePaymentSyncRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await sync_customer_stripe_checkout_session(orderId, payload.sessionId, current_user)
    return success_response("Stripe checkout synced successfully.", customer_payment_result(data))


@router.get("/transactions/{orderId}/payments/{paymentRecordId}/receipt", response_class=HTMLResponse)
async def customer_payment_receipt(orderId: str, paymentRecordId: str, current_user: dict = Depends(get_current_customer_user)):
    html = await get_customer_payment_receipt_html(orderId, paymentRecordId, current_user)
    return HTMLResponse(content=html)


@router.get("/transactions/{orderId}")
async def transaction_detail(orderId: str, current_user: dict = Depends(get_current_customer_user)):
    data = await get_customer_transaction(orderId, current_user)
    return success_response("Customer transaction fetched successfully.", data)


@router.post("/transactions/{orderId}/reorder")
async def reorder_transaction(orderId: str, current_user: dict = Depends(get_current_customer_user)):
    data = await reorder_customer_transaction(orderId, current_user)
    return success_response("Transaction reordered successfully.", data)


@router.get("/orders/{orderId}")
async def order_detail(orderId: str, current_user: dict = Depends(get_current_customer_user)):
    data = await get_customer_order(orderId, current_user)
    return success_response("Customer transaction fetched successfully.", data)


@router.get("/notifications")
async def notifications(page: int = 1, limit: int = 20, current_user: dict = Depends(get_current_customer_user)):
    data = await list_customer_notifications(current_user, page, limit)
    return success_response("Customer notifications fetched successfully.", data["items"], data["pagination"])


@router.post("/notifications/{notificationId}/read")
async def read_notification(notificationId: str, current_user: dict = Depends(get_current_customer_user)):
    data = await mark_customer_notification_read(notificationId, current_user)
    return success_response("Customer notification updated successfully.", data)


@router.post("/notifications/read-all")
async def read_all_notifications(current_user: dict = Depends(get_current_customer_user)):
    data = await mark_all_customer_notifications_read(current_user)
    return success_response("Customer notifications marked as read.", data)
