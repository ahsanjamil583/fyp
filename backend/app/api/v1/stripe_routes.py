from fastapi import APIRouter, Request

from app.core.responses import success_response
from app.services.payment_service import process_stripe_webhook

router = APIRouter(prefix="/payments/stripe", tags=["stripe-payments"])


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    data = await process_stripe_webhook(payload, signature)
    return success_response("Stripe webhook processed successfully.", data)
