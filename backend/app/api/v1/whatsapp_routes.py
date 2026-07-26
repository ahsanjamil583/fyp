from fastapi import APIRouter, Depends, Query, Request
from fastapi import HTTPException, status
from fastapi.responses import PlainTextResponse

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.whatsapp_schema import WhatsAppEmbeddedSignupCaptureRequest, WhatsAppMockInboundRequest, WhatsAppOutboundRequest, WhatsAppPhoneRegistrationRequest, WhatsAppSettingsRequest, WhatsAppWebhookRoutingTestRequest, WhatsAppLiveWebhookTestRequest, WhatsAppGoLiveTestRunRequest
from app.services.whatsapp_service import (
    capture_embedded_signup_response,
    disconnect_whatsapp_settings,
    exchange_embedded_signup_token,
    get_whatsapp_settings_for_owner,
    get_whatsapp_webhook_routing_status,
    get_whatsapp_live_diagnostics,
    get_whatsapp_conversation_timeline,
    get_whatsapp_go_live_checklist,
    list_whatsapp_conversations,
    process_whatsapp_webhook_payload,
    run_whatsapp_live_webhook_test,
    record_whatsapp_go_live_test_run,
    register_embedded_signup_phone_number,
    send_owner_whatsapp_test,
    simulate_whatsapp_inbound,
    subscribe_embedded_signup_webhooks,
    test_whatsapp_webhook_routing_for_owner,
    upsert_whatsapp_settings,
    verify_whatsapp_webhook,
)

router = APIRouter(tags=["whatsapp-agent"])


@router.get("/webhooks/whatsapp")
async def whatsapp_webhook_verify(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    challenge_text = await verify_whatsapp_webhook(mode, verify_token, challenge)
    return PlainTextResponse(challenge_text)


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook_receive(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WhatsApp webhook payload.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WhatsApp webhook payload.")
    data = await process_whatsapp_webhook_payload(payload)
    return success_response("WhatsApp webhook processed successfully.", data)


@router.get("/tenants/{tenantId}/whatsapp/settings")
async def whatsapp_settings(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await get_whatsapp_settings_for_owner(tenantId, current_user)
    return success_response("WhatsApp settings fetched successfully.", data)


@router.put("/tenants/{tenantId}/whatsapp/settings")
async def save_whatsapp_settings(
    tenantId: str,
    payload: WhatsAppSettingsRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await upsert_whatsapp_settings(tenantId, payload, current_user)
    return success_response("WhatsApp agent connected successfully.", data)


@router.post("/tenants/{tenantId}/whatsapp/disconnect")
async def disconnect_whatsapp(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await disconnect_whatsapp_settings(tenantId, current_user)
    return success_response("WhatsApp agent disconnected successfully.", data)


@router.post("/tenants/{tenantId}/whatsapp/embedded-signup/capture")
async def capture_embedded_signup(
    tenantId: str,
    payload: WhatsAppEmbeddedSignupCaptureRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await capture_embedded_signup_response(tenantId, payload, current_user)
    return success_response("Meta Embedded Signup response captured successfully.", data)


@router.post("/tenants/{tenantId}/whatsapp/embedded-signup/exchange-token")
async def exchange_embedded_signup(
    tenantId: str,
    current_user: dict = Depends(get_current_business_user),
):
    data = await exchange_embedded_signup_token(tenantId, current_user)
    return success_response("Meta Embedded Signup token exchanged successfully.", data)


@router.post("/tenants/{tenantId}/whatsapp/embedded-signup/subscribe-webhooks")
async def subscribe_embedded_signup_webhooks_route(
    tenantId: str,
    current_user: dict = Depends(get_current_business_user),
):
    data = await subscribe_embedded_signup_webhooks(tenantId, current_user)
    return success_response("Meta WABA webhooks subscribed successfully.", data)


@router.post("/tenants/{tenantId}/whatsapp/embedded-signup/register-phone")
async def register_embedded_signup_phone_route(
    tenantId: str,
    payload: WhatsAppPhoneRegistrationRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await register_embedded_signup_phone_number(tenantId, payload, current_user)
    return success_response("Meta WhatsApp phone number registered successfully.", data)




@router.get("/tenants/{tenantId}/whatsapp/embedded-signup/routing-status")
async def whatsapp_embedded_signup_routing_status(
    tenantId: str,
    current_user: dict = Depends(get_current_business_user),
):
    data = await get_whatsapp_webhook_routing_status(tenantId, current_user)
    return success_response("Meta WhatsApp webhook routing status fetched successfully.", data)


@router.post("/tenants/{tenantId}/whatsapp/embedded-signup/test-routing")
async def whatsapp_embedded_signup_test_routing(
    tenantId: str,
    payload: WhatsAppWebhookRoutingTestRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await test_whatsapp_webhook_routing_for_owner(tenantId, payload, current_user)
    return success_response("Meta WhatsApp Phone Number ID routing test completed successfully.", data)

@router.get("/tenants/{tenantId}/whatsapp/diagnostics")
async def whatsapp_live_diagnostics(
    tenantId: str,
    current_user: dict = Depends(get_current_business_user),
):
    data = await get_whatsapp_live_diagnostics(tenantId, current_user)
    return success_response("WhatsApp live diagnostics fetched successfully.", data)


@router.post("/tenants/{tenantId}/whatsapp/diagnostics/test-webhook-payload")
async def whatsapp_live_webhook_test(
    tenantId: str,
    payload: WhatsAppLiveWebhookTestRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await run_whatsapp_live_webhook_test(tenantId, payload, current_user)
    return success_response("WhatsApp live webhook test completed successfully.", data)


@router.get("/tenants/{tenantId}/whatsapp/conversations/{conversationId}/timeline")
async def whatsapp_conversation_timeline(
    tenantId: str,
    conversationId: str,
    current_user: dict = Depends(get_current_business_user),
):
    data = await get_whatsapp_conversation_timeline(tenantId, conversationId, current_user)
    return success_response("WhatsApp conversation timeline fetched successfully.", data)




@router.get("/tenants/{tenantId}/whatsapp/go-live/checklist")
async def whatsapp_go_live_checklist(
    tenantId: str,
    current_user: dict = Depends(get_current_business_user),
):
    data = await get_whatsapp_go_live_checklist(tenantId, current_user)
    return success_response("WhatsApp Phase J go-live checklist fetched successfully.", data)


@router.post("/tenants/{tenantId}/whatsapp/go-live/test-run")
async def whatsapp_go_live_test_run(
    tenantId: str,
    payload: WhatsAppGoLiveTestRunRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await record_whatsapp_go_live_test_run(tenantId, payload, current_user)
    return success_response("WhatsApp Phase J go-live test run recorded successfully.", data)


@router.get("/tenants/{tenantId}/whatsapp/conversations")
async def whatsapp_conversations(
    tenantId: str,
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(get_current_business_user),
):
    data = await list_whatsapp_conversations(tenantId, current_user, page, limit)
    return success_response("WhatsApp conversations fetched successfully.", data["items"], data["pagination"] | {"tenant": data["tenant"]})


@router.post("/tenants/{tenantId}/whatsapp/mock/inbound")
async def whatsapp_mock_inbound(
    tenantId: str,
    payload: WhatsAppMockInboundRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await simulate_whatsapp_inbound(tenantId, payload, current_user)
    return success_response("Mock WhatsApp inbound message processed successfully.", data)


@router.post("/tenants/{tenantId}/whatsapp/send-test")
async def whatsapp_send_test(
    tenantId: str,
    payload: WhatsAppOutboundRequest,
    current_user: dict = Depends(get_current_business_user),
):
    data = await send_owner_whatsapp_test(tenantId, payload, current_user)
    return success_response("WhatsApp test message processed successfully.", data)
