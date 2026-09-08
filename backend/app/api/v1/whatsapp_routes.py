import logging

from fastapi import APIRouter, Depends, Header

from app.core.responses import success_response
from app.core.security import get_current_business_user
from app.schemas.whatsapp_schema import (
    WhatsAppBridgeInboundRequest,
    WhatsAppBridgeStatusRequest,
    WhatsAppMockInboundRequest,
    WhatsAppOutboundRequest,
    WhatsAppSettingsRequest,
)
from app.services.whatsapp_service import (
    disconnect_whatsapp_settings,
    get_whatsapp_settings_for_owner,
    list_whatsapp_conversations,
    process_bridge_inbound,
    process_bridge_status,
    refresh_whatsapp_bridge_token,
    send_owner_whatsapp_test,
    simulate_whatsapp_inbound,
    upsert_whatsapp_settings,
)

router = APIRouter(tags=["whatsapp-agent"])
logger = logging.getLogger(__name__)


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


@router.post("/tenants/{tenantId}/whatsapp/bridge-token")
async def whatsapp_refresh_bridge_token(tenantId: str, current_user: dict = Depends(get_current_business_user)):
    data = await refresh_whatsapp_bridge_token(tenantId, current_user)
    return success_response("WhatsApp bridge token refreshed successfully.", data)


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


@router.post("/whatsapp/bridge/status")
async def whatsapp_bridge_status(
    payload: WhatsAppBridgeStatusRequest,
    x_bizxus_bridge_token: str = Header(default="", alias="X-BizXus-Bridge-Token"),
):
    data = await process_bridge_status(payload, x_bizxus_bridge_token)
    return success_response("WhatsApp bridge status updated successfully.", data)


@router.post("/whatsapp/bridge/inbound")
async def whatsapp_bridge_inbound(
    payload: WhatsAppBridgeInboundRequest,
    x_bizxus_bridge_token: str = Header(default="", alias="X-BizXus-Bridge-Token"),
):
    data = await process_bridge_inbound(payload, x_bizxus_bridge_token)
    return success_response("WhatsApp bridge inbound message processed successfully.", data)
