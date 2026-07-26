from __future__ import annotations

import re
import secrets
import logging
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import HTTPException, status
import httpx

from app.core.config import settings
from app.core.module_guard import ensure_tenant_module_enabled, ensure_tenant_module_usage_available
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.integrations.whatsapp.provider import WhatsAppSendError, send_whatsapp_text
from app.schemas.whatsapp_schema import WhatsAppMockInboundRequest, WhatsAppOutboundRequest, WhatsAppPhoneRegistrationRequest, WhatsAppSettingsRequest, WhatsAppWebhookRoutingTestRequest, WhatsAppLiveWebhookTestRequest
from app.services.ai_chat_service import build_ai_reply, detect_language_mode, load_conversation_messages, save_message
from app.services.business_notification_service import create_business_notification
from app.services.category_config_service import validate_tenant_fulfillment
from app.services.customer_service import sync_customer_stats_for_transaction
from app.services.custom_field_service import validate_custom_values_for_tenant_oid
from app.services.inventory_service import reserve_transaction_stock
from app.services.order_validation_service import normalize_fulfillment, normalize_notes
from app.services.payment_service import get_customer_payment_options_for_tenant, normalize_customer_payment_preference
from app.services.smart_order_service import resolve_requested_order_items
from app.services.system_validation_service import build_meta_embedded_signup_readiness
from app.services.transaction_number_service import generate_transaction_number
from app.services.transaction_workflow_service import get_initial_payment_status, get_initial_transaction_status, infer_transaction_type, normalize_transaction_type

HANDOFF_REPLY = (
    "I have marked this conversation for owner handoff. The business team can review it from the dashboard."
)
DEFAULT_FALLBACK_REPLY = (
    "Sorry, main is waqt WhatsApp reply complete nahi kar pa raha. Business owner ko notify kar diya gaya hai."
)
DEFAULT_HANDOFF_KEYWORDS = ["human", "agent", "admin", "owner", "representative", "call me", "insan", "baat karni"]
logger = logging.getLogger(__name__)


def normalize_phone(value: str | None) -> str:
    phone = re.sub(r"[^0-9+]", "", str(value or "").strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if phone and not phone.startswith("+"):
        # Pakistan-friendly default for local FYP demos.
        if phone.startswith("0") and len(phone) >= 10:
            phone = "+92" + phone[1:]
        elif phone.startswith("92"):
            phone = "+" + phone
    return phone


def _digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _same_normalized_phone(left: str | None, right: str | None) -> bool:
    return bool(normalize_phone(left)) and normalize_phone(left) == normalize_phone(right)


def _phone_id_query(phone_number_id: str) -> dict:
    return {"phoneNumberId": str(phone_number_id or "").strip(), "isConnected": True}


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    value = str(value)
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _first_present(*values) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _nested_get(data: dict, *keys: str) -> str:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return _first_present(current)


def _extract_embedded_signup_fields(payload) -> dict:
    auth_response = payload.authResponse or {}
    embedded = payload.embeddedSignup or {}
    embedded_data = embedded.get("data") if isinstance(embedded.get("data"), dict) else {}
    callback_query = payload.callbackQuery or {}
    authorization_code = _first_present(
        payload.authorizationCode,
        auth_response.get("code"),
        callback_query.get("code"),
    )
    waba_id = _first_present(
        embedded_data.get("waba_id"),
        embedded_data.get("wabaId"),
        embedded_data.get("whatsapp_business_account_id"),
        embedded_data.get("whatsappBusinessAccountId"),
        _nested_get(embedded_data, "waba", "id"),
    )
    phone_number_id = _first_present(
        embedded_data.get("phone_number_id"),
        embedded_data.get("phoneNumberId"),
        embedded_data.get("phone_number_id_selected"),
        _nested_get(embedded_data, "phone_number", "id"),
    )
    business_number = _first_present(
        embedded_data.get("business_phone_number"),
        embedded_data.get("businessPhoneNumber"),
        embedded_data.get("phone_number"),
        embedded_data.get("display_phone_number"),
        _nested_get(embedded_data, "phone_number", "display_phone_number"),
    )
    meta_business_id = _first_present(
        embedded_data.get("business_id"),
        embedded_data.get("businessId"),
        embedded_data.get("meta_business_id"),
        embedded_data.get("metaBusinessId"),
    )
    return {
        "authorizationCode": authorization_code,
        "wabaId": waba_id,
        "phoneNumberId": phone_number_id,
        "businessWhatsAppNumber": business_number,
        "normalizedBusinessWhatsAppNumber": normalize_phone(business_number),
        "metaBusinessId": meta_business_id,
        "embeddedSignupEvent": embedded.get("event") or "",
    }


def _meta_graph_base_url(api_version: str | None = None) -> str:
    version = api_version or settings.meta_graph_api_version or settings.whatsapp_api_version
    version = version if str(version).startswith("v") else f"v{version}"
    return f"https://graph.facebook.com/{version}"


def _frontend_callback_url() -> str:
    base = (settings.frontend_base_url or "").rstrip("/")
    path = settings.meta_business_login_redirect_path or "/dashboard/whatsapp-agent/connect/callback"
    if not base:
        return ""
    return f"{base}{path if path.startswith('/') else f'/{path}'}"


async def _exchange_meta_authorization_code(authorization_code: str) -> dict:
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta App ID and App Secret are required before exchanging the WhatsApp signup code.",
        )
    params = {
        "client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret,
        "code": authorization_code,
    }
    redirect_uri = _frontend_callback_url()
    if redirect_uri:
        params["redirect_uri"] = redirect_uri
    endpoint = f"{_meta_graph_base_url()}/oauth/access_token"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        detail = "Meta rejected the authorization code during token exchange."
        try:
            meta_error = exc.response.json().get("error") or {}
            detail = meta_error.get("message") or detail
        except Exception:
            pass
        logger.warning(
            "Meta WhatsApp token exchange failed: status=%s app_id_present=%s redirect_uri=%s error=%s",
            exc.response.status_code,
            bool(settings.meta_app_id),
            redirect_uri,
            detail,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Meta token exchange failed: {detail}") from exc
    except Exception as exc:
        logger.exception("Meta WhatsApp token exchange request failed: app_id_present=%s redirect_uri=%s", bool(settings.meta_app_id), redirect_uri)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to exchange Meta authorization code right now.") from exc
    if not isinstance(data, dict) or not data.get("access_token"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Meta token exchange did not return an access token.")
    return data


async def _fetch_meta_phone_number_details(phone_number_id: str, access_token: str, api_version: str) -> dict:
    if not phone_number_id or not access_token:
        return {}
    endpoint = f"{_meta_graph_base_url(api_version)}/{phone_number_id}"
    params = {
        "fields": "display_phone_number,verified_name,code_verification_status,quality_rating",
        "access_token": access_token,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Unable to fetch Meta phone details after token exchange: phone_number_id=%s error=%s", phone_number_id, exc)
        return {}


def _safe_meta_error(response: httpx.Response, fallback: str) -> str:
    try:
        meta_error = response.json().get("error") or {}
        return str(meta_error.get("message") or meta_error.get("error_user_msg") or fallback)
    except Exception:
        return fallback


def _public_webhook_callback_url() -> str:
    base = (settings.backend_public_url or "").rstrip("/")
    if not base:
        return ""
    return f"{base}{settings.api_v1_prefix}/webhooks/whatsapp"


async def _post_meta_waba_webhook_subscription(
    *,
    waba_id: str,
    access_token: str,
    api_version: str,
    callback_url: str = "",
    verify_token: str = "",
) -> dict:
    """Subscribe this app to a customer's WhatsApp Business Account webhooks.

    Meta's WABA subscription endpoint is POST /{WABA_ID}/subscribed_apps.
    The optional override_callback_uri/verify_token fields are sent when available so
    local/ngrok and deployed tenant-specific callbacks can be validated from the
    stored integration record.
    """
    if not waba_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WhatsApp Business Account ID is required before webhook subscription.")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meta business access token is required before webhook subscription.")

    endpoint = f"{_meta_graph_base_url(api_version)}/{waba_id}/subscribed_apps"
    payload: dict[str, str] = {}
    if callback_url:
        payload["override_callback_uri"] = callback_url
    if verify_token:
        payload["verify_token"] = verify_token

    params = {"access_token": access_token}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            # Some Meta app configurations accept JSON body for callback override,
            # and some accept a plain POST with access_token only. First try the
            # richer request, then fall back to an access-token-only subscription
            # if Meta rejects callback override fields.
            response = await client.post(endpoint, params=params, json=payload or None)
            if response.status_code >= 400 and payload:
                fallback_response = await client.post(endpoint, params=params)
                if fallback_response.status_code < 400:
                    response = fallback_response
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        detail = _safe_meta_error(exc.response, "Meta rejected the WABA webhook subscription request.")
        logger.warning(
            "Meta WABA webhook subscription failed: status=%s waba_id=%s callback_present=%s error=%s",
            exc.response.status_code,
            waba_id,
            bool(callback_url),
            detail,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Meta webhook subscription failed: {detail}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Meta WABA webhook subscription request failed: waba_id=%s callback_present=%s", waba_id, bool(callback_url))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to subscribe this WhatsApp Business Account to webhooks right now.") from exc

    if not isinstance(data, dict):
        data = {"success": True, "raw": data}
    return data


async def _post_meta_phone_number_registration(
    *,
    phone_number_id: str,
    access_token: str,
    api_version: str,
    pin: str,
) -> dict:
    """Register a verified WhatsApp business phone number for Cloud API use.

    Meta Cloud API registration uses POST /{PHONE_NUMBER_ID}/register with
    messaging_product=whatsapp and a 6-digit two-step verification PIN. The
    PIN is never persisted by BizXusAI; it is sent once to Meta from the owner
    dashboard request.
    """
    if not phone_number_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meta Phone Number ID is required before phone registration.")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meta business access token is required before phone registration.")
    pin = str(pin or "").strip()
    if not re.fullmatch(r"[0-9]{6}", pin):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid 6-digit WhatsApp registration PIN.")

    endpoint = f"{_meta_graph_base_url(api_version)}/{phone_number_id}/register"
    payload = {"messaging_product": "whatsapp", "pin": pin}
    params = {"access_token": access_token}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(endpoint, params=params, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        detail = _safe_meta_error(exc.response, "Meta rejected the phone number registration request.")
        logger.warning(
            "Meta phone registration failed: status=%s phone_number_id=%s error=%s",
            exc.response.status_code,
            phone_number_id,
            detail,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Meta phone registration failed: {detail}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Meta phone registration request failed: phone_number_id=%s", phone_number_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to register this WhatsApp phone number right now.") from exc

    if not isinstance(data, dict):
        data = {"success": True, "raw": data}
    return data


def serialize_whatsapp_settings(settings_doc: dict | None, tenant: dict | None = None) -> dict:
    if not settings_doc:
        tenant_contact = (tenant or {}).get("contact") or {}
        business_number = tenant_contact.get("whatsapp") or ""
        return {
            "id": "",
            "tenantId": str((tenant or {}).get("_id", "")),
            "provider": settings.whatsapp_provider,
            "businessWhatsAppNumber": business_number,
            "normalizedBusinessWhatsAppNumber": normalize_phone(business_number),
            "displayName": (tenant or {}).get("name", ""),
            "phoneNumberId": settings.whatsapp_phone_number_id,
            "whatsappBusinessAccountId": "",
            "apiVersion": settings.whatsapp_api_version,
            "webhookVerifyToken": settings.whatsapp_verify_token,
            "accessTokenMasked": "",
            "hasAccessToken": bool(settings.whatsapp_access_token),
            "isConnected": False,
            "agentEnabled": True,
            "autoReplyEnabled": True,
            "handoffEnabled": True,
            "handoffKeywords": DEFAULT_HANDOFF_KEYWORDS,
            "welcomeMessage": "Assalam o Alaikum! Main BizXus AI assistant hoon. Aap products, prices, timing ya order ke bare mein pooch sakte hain.",
            "fallbackReply": DEFAULT_FALLBACK_REPLY,
            "businessHoursMode": "always_on",
            "status": "not_configured",
            "lastInboundAt": None,
            "lastOutboundAt": None,
        }
    data = serialize_document(settings_doc)
    data["accessTokenMasked"] = mask_secret(settings_doc.get("accessToken"))
    data["authorizationCodeMasked"] = mask_secret(settings_doc.get("authorizationCode"))
    data["hasAccessToken"] = bool(settings_doc.get("accessToken") or settings.whatsapp_access_token)
    data["hasPendingAuthorizationCode"] = bool(settings_doc.get("authorizationCode"))
    data.pop("accessToken", None)
    data.pop("authorizationCode", None)
    data.pop("rawSignupResponse", None)
    return data


def build_whatsapp_deep_link(phone: str | None, text: str = "") -> str:
    digits = re.sub(r"\D", "", normalize_phone(phone))
    if not digits:
        return ""
    url = f"https://wa.me/{digits}"
    if text:
        from urllib.parse import quote

        url = f"{url}?text={quote(text)}"
    return url


async def get_customer_facing_whatsapp_agent(tenant: dict) -> dict:
    """Return safe WhatsApp Agent contact details for public/customer pages."""
    db = get_database()
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant["_id"], "isConnected": True})
    contact = tenant.get("contact") or {}
    enabled_modules = set(tenant.get("enabledModuleCodes") or [])
    integration_number = ""
    if integration:
        integration_number = integration.get("businessWhatsAppNumber") or integration.get("normalizedBusinessWhatsAppNumber") or ""
    business_number = integration_number or contact.get("whatsapp") or ""
    normalized_number = normalize_phone(business_number)
    agent_enabled = bool((integration or {}).get("agentEnabled", True)) if integration else False
    auto_reply_enabled = bool((integration or {}).get("autoReplyEnabled", True)) if integration else False
    provider = (integration or {}).get("provider", "")
    provider_ready = provider == "meta_cloud" and bool((integration or {}).get("phoneNumberId"))
    module_ready = "whatsapp_agent" in enabled_modules and "ai_chat" in enabled_modules
    agent_ready = bool(integration and provider_ready and module_ready and agent_enabled and auto_reply_enabled and normalized_number)
    enabled = bool(normalized_number)
    default_text = "Hello, I found your business on BizXusAI and I want to ask about your products."
    return {
        "enabled": enabled,
        "configured": bool(integration),
        "status": (integration or {}).get("status", "not_configured"),
        "provider": provider,
        "providerReady": provider_ready,
        "agentReady": agent_ready,
        "displayName": (integration or {}).get("displayName") or tenant.get("name", ""),
        "businessWhatsAppNumber": business_number,
        "normalizedBusinessWhatsAppNumber": normalized_number,
        "waLink": build_whatsapp_deep_link(normalized_number, default_text),
        "autoReplyEnabled": auto_reply_enabled,
        "agentEnabled": agent_enabled,
        "messageHint": (
            "Message the AI assistant on WhatsApp for products, prices, stock, delivery, and orders."
            if agent_ready
            else "Chat with this business on WhatsApp."
            if enabled
            else "This business has not added a WhatsApp number yet."
        ),
    }


async def _get_tenant_for_whatsapp_owner(tenant_id: str, user: dict) -> tuple[ObjectId, dict]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "whatsapp_agent")
    await ensure_tenant_module_enabled(tenant_oid, "ai_chat")
    return tenant_oid, tenant


async def get_whatsapp_settings_for_owner(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    settings_doc = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    return {
        "tenant": serialize_document(tenant),
        "settings": serialize_whatsapp_settings(settings_doc, tenant),
        "metaEmbeddedSignup": build_meta_embedded_signup_readiness(),
    }


async def upsert_whatsapp_settings(tenant_id: str, payload: WhatsAppSettingsRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    now = datetime.now(timezone.utc)
    existing = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    normalized_number = normalize_phone(payload.businessWhatsAppNumber)
    if not normalized_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a valid WhatsApp number.")

    has_meta_token = bool(payload.accessToken.strip() or (existing or {}).get("accessToken") or settings.whatsapp_access_token)
    if payload.provider == "meta_cloud":
        if not payload.phoneNumberId.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone Number ID is required for Meta WhatsApp Cloud API.")
        if not has_meta_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Access token is required for Meta WhatsApp Cloud API.")
        duplicate_phone_id = await db.whatsapp_integrations.find_one(
            {
                "tenantId": {"$ne": tenant_oid},
                "provider": "meta_cloud",
                "phoneNumberId": payload.phoneNumberId.strip(),
                "isConnected": True,
            }
        )
        if duplicate_phone_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This Meta WhatsApp Phone Number ID is already connected to another business. Each business needs its own connected WhatsApp number.",
            )

    webhook_token = existing.get("webhookVerifyToken") if existing else ""
    if not webhook_token:
        webhook_token = secrets.token_urlsafe(24)

    update_doc = {
        "tenantId": tenant_oid,
        "provider": payload.provider,
        "businessWhatsAppNumber": payload.businessWhatsAppNumber,
        "normalizedBusinessWhatsAppNumber": normalized_number,
        "displayName": payload.displayName or tenant.get("name", ""),
        "phoneNumberId": payload.phoneNumberId.strip(),
        "whatsappBusinessAccountId": payload.whatsappBusinessAccountId.strip(),
        "apiVersion": payload.apiVersion.strip() or settings.whatsapp_api_version,
        "webhookVerifyToken": webhook_token,
        "agentEnabled": payload.agentEnabled,
        "autoReplyEnabled": payload.autoReplyEnabled,
        "handoffEnabled": payload.handoffEnabled,
        "handoffKeywords": [str(word).strip().lower() for word in payload.handoffKeywords if str(word).strip()],
        "welcomeMessage": payload.welcomeMessage.strip(),
        "fallbackReply": payload.fallbackReply.strip() or DEFAULT_FALLBACK_REPLY,
        "businessHoursMode": payload.businessHoursMode,
        "isConnected": True,
        "status": "connected_mock" if payload.provider == "mock" else "connected_meta_cloud",
        "updatedAt": now,
    }
    if payload.accessToken.strip():
        update_doc["accessToken"] = payload.accessToken.strip()
    elif not existing:
        update_doc["accessToken"] = ""

    await db.whatsapp_integrations.update_one(
        {"tenantId": tenant_oid},
        {"$set": update_doc, "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )
    settings_doc = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    return {"tenant": serialize_document(tenant), "settings": serialize_whatsapp_settings(settings_doc, tenant)}


async def capture_embedded_signup_response(tenant_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    now = datetime.now(timezone.utc)
    existing = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    extracted = _extract_embedded_signup_fields(payload)
    authorization_code = extracted["authorizationCode"]
    if not authorization_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Meta signup response did not include an authorization code. Complete Embedded Signup again.",
        )
    if extracted["phoneNumberId"]:
        duplicate_phone_id = await db.whatsapp_integrations.find_one(
            {
                "tenantId": {"$ne": tenant_oid},
                "provider": "meta_cloud",
                "phoneNumberId": extracted["phoneNumberId"],
                "isConnected": True,
            }
        )
        if duplicate_phone_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This Meta WhatsApp Phone Number ID is already connected to another business.",
            )

    webhook_token = (existing or {}).get("webhookVerifyToken") or secrets.token_urlsafe(24)
    update_doc = {
        "tenantId": tenant_oid,
        "provider": "meta_cloud",
        "connectionStatus": "pending_token_exchange",
        "status": "pending_token_exchange",
        "isConnected": False,
        "authorizationCode": authorization_code,
        "authorizationCodeCapturedAt": now,
        "webhookVerifyToken": webhook_token,
        "apiVersion": settings.meta_graph_api_version or settings.whatsapp_api_version,
        "agentEnabled": (existing or {}).get("agentEnabled", True),
        "autoReplyEnabled": (existing or {}).get("autoReplyEnabled", True),
        "handoffEnabled": (existing or {}).get("handoffEnabled", True),
        "handoffKeywords": (existing or {}).get("handoffKeywords") or DEFAULT_HANDOFF_KEYWORDS,
        "welcomeMessage": (existing or {}).get("welcomeMessage")
        or "Assalam o Alaikum! Main BizXus AI assistant hoon. Aap products, prices, timing ya order ke bare mein pooch sakte hain.",
        "fallbackReply": (existing or {}).get("fallbackReply") or DEFAULT_FALLBACK_REPLY,
        "businessHoursMode": (existing or {}).get("businessHoursMode") or "always_on",
        "embeddedSignup": payload.embeddedSignup,
        "signupSource": payload.source,
        "signupStatus": payload.status,
        "signupReceivedAt": payload.receivedAt,
        "rawSignupResponse": {
            "source": payload.source,
            "status": payload.status,
            "authResponse": {key: value for key, value in (payload.authResponse or {}).items() if key != "code"},
            "embeddedSignup": payload.embeddedSignup,
            "callbackQuery": {key: value for key, value in (payload.callbackQuery or {}).items() if key != "code"},
            "receivedAt": payload.receivedAt,
        },
        "updatedAt": now,
    }
    for field in ["wabaId", "phoneNumberId", "businessWhatsAppNumber", "normalizedBusinessWhatsAppNumber", "metaBusinessId"]:
        if extracted[field]:
            update_doc[field] = extracted[field]
    if extracted["wabaId"]:
        update_doc["whatsappBusinessAccountId"] = extracted["wabaId"]
    if not update_doc.get("businessWhatsAppNumber"):
        contact_whatsapp = ((tenant.get("contact") or {}).get("whatsapp") or "").strip()
        if contact_whatsapp:
            update_doc["businessWhatsAppNumber"] = contact_whatsapp
            update_doc["normalizedBusinessWhatsAppNumber"] = normalize_phone(contact_whatsapp)

    await db.whatsapp_integrations.update_one(
        {"tenantId": tenant_oid},
        {"$set": update_doc, "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )
    settings_doc = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    return {
        "tenant": serialize_document(tenant),
        "settings": serialize_whatsapp_settings(settings_doc, tenant),
        "metaEmbeddedSignup": build_meta_embedded_signup_readiness(),
        "nextStep": "phase_d_token_exchange",
    }


async def exchange_embedded_signup_token(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    now = datetime.now(timezone.utc)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Meta signup response is saved for this business.")
    authorization_code = (integration.get("authorizationCode") or "").strip()
    if not authorization_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending Meta authorization code found. Complete Embedded Signup and save the response first.",
        )
    if integration.get("provider") != "meta_cloud":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This business is not in Meta Cloud signup mode.")

    try:
        token_data = await _exchange_meta_authorization_code(authorization_code)
    except HTTPException as exc:
        await db.whatsapp_integrations.update_one(
            {"_id": integration["_id"]},
            {
                "$set": {
                    "connectionStatus": "token_exchange_failed",
                    "status": "token_exchange_failed",
                    "isConnected": False,
                    "lastError": str(exc.detail),
                    "lastErrorAt": now,
                    "updatedAt": now,
                }
            },
        )
        raise

    access_token = token_data["access_token"]
    api_version = integration.get("apiVersion") or settings.meta_graph_api_version or settings.whatsapp_api_version
    phone_details = await _fetch_meta_phone_number_details(integration.get("phoneNumberId", ""), access_token, api_version)
    business_number = (
        phone_details.get("display_phone_number")
        or integration.get("businessWhatsAppNumber")
        or integration.get("normalizedBusinessWhatsAppNumber")
        or ""
    )
    normalized_number = normalize_phone(business_number)
    expires_in = token_data.get("expires_in")
    token_expires_at = None
    if isinstance(expires_in, int) and expires_in > 0:
        from datetime import timedelta

        token_expires_at = now + timedelta(seconds=expires_in)

    update_doc = {
        "provider": "meta_cloud",
        "accessToken": access_token,
        "accessTokenType": token_data.get("token_type") or "bearer",
        "tokenExchangeResponse": {
            "tokenType": token_data.get("token_type") or "bearer",
            "expiresIn": expires_in,
        },
        "tokenExchangedAt": now,
        "tokenExpiresAt": token_expires_at,
        "connectionStatus": "token_exchanged",
        "status": "connected_meta_cloud",
        "isConnected": True,
        "webhookSubscriptionStatus": integration.get("webhookSubscriptionStatus") or "pending",
        "phoneRegistrationStatus": integration.get("phoneRegistrationStatus") or "pending",
        "lastConnectedAt": now,
        "lastError": "",
        "lastErrorAt": None,
        "updatedAt": now,
    }
    if business_number:
        update_doc["businessWhatsAppNumber"] = business_number
    if normalized_number:
        update_doc["normalizedBusinessWhatsAppNumber"] = normalized_number
    if phone_details:
        update_doc["phoneNumberDetails"] = phone_details
        if phone_details.get("verified_name"):
            update_doc["displayName"] = phone_details["verified_name"]

    await db.whatsapp_integrations.update_one({"_id": integration["_id"]}, {"$set": update_doc, "$unset": {"authorizationCode": ""}})
    settings_doc = await db.whatsapp_integrations.find_one({"_id": integration["_id"]})
    return {
        "tenant": serialize_document(tenant),
        "settings": serialize_whatsapp_settings(settings_doc, tenant),
        "metaEmbeddedSignup": build_meta_embedded_signup_readiness(),
        "nextStep": "phase_e_subscribe_webhooks",
        "tokenExchange": {
            "status": "token_exchanged",
            "hasAccessToken": True,
            "tokenExpiresAt": token_expires_at.isoformat() if token_expires_at else None,
            "phoneDetailsFetched": bool(phone_details),
        },
    }


async def subscribe_embedded_signup_webhooks(tenant_id: str, user: dict) -> dict:
    """Phase E: subscribe the connected customer's WABA to this app's WhatsApp webhooks."""
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    now = datetime.now(timezone.utc)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Meta WhatsApp connection found for this business.")
    if integration.get("provider") != "meta_cloud":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook subscription is available only for Meta Cloud connections.")

    access_token = (integration.get("accessToken") or "").strip()
    if not access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exchange the Meta signup code for a business token before subscribing webhooks.")
    waba_id = (integration.get("wabaId") or integration.get("whatsappBusinessAccountId") or "").strip()
    if not waba_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WABA ID is missing. Complete Embedded Signup again or save the WhatsApp Business Account ID.")

    api_version = integration.get("apiVersion") or settings.meta_graph_api_version or settings.whatsapp_api_version
    callback_url = _public_webhook_callback_url()
    if not callback_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="BACKEND_PUBLIC_URL is required before subscribing Meta webhooks.")
    verify_token = integration.get("webhookVerifyToken") or settings.whatsapp_verify_token
    if not verify_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook verify token is required before subscribing Meta webhooks.")

    await db.whatsapp_integrations.update_one(
        {"_id": integration["_id"]},
        {
            "$set": {
                "webhookSubscriptionStatus": "subscribing",
                "webhookSubscriptionAttemptedAt": now,
                "webhookCallbackUrl": callback_url,
                "updatedAt": now,
            }
        },
    )

    try:
        provider_response = await _post_meta_waba_webhook_subscription(
            waba_id=waba_id,
            access_token=access_token,
            api_version=api_version,
            callback_url=callback_url,
            verify_token=verify_token,
        )
    except HTTPException as exc:
        await db.whatsapp_integrations.update_one(
            {"_id": integration["_id"]},
            {
                "$set": {
                    "webhookSubscriptionStatus": "failed",
                    "connectionStatus": "webhook_subscription_failed",
                    "lastError": str(exc.detail),
                    "lastErrorAt": datetime.now(timezone.utc),
                    "updatedAt": datetime.now(timezone.utc),
                }
            },
        )
        raise

    subscribed_now = datetime.now(timezone.utc)
    await db.whatsapp_integrations.update_one(
        {"_id": integration["_id"]},
        {
            "$set": {
                "webhookSubscriptionStatus": "subscribed",
                "webhookSubscribedAt": subscribed_now,
                "webhookCallbackUrl": callback_url,
                "webhookProviderResponse": provider_response,
                "connectionStatus": "webhook_subscribed",
                "status": "connected_meta_cloud",
                "isConnected": True,
                "lastError": "",
                "lastErrorAt": None,
                "updatedAt": subscribed_now,
            }
        },
    )
    settings_doc = await db.whatsapp_integrations.find_one({"_id": integration["_id"]})
    return {
        "tenant": serialize_document(tenant),
        "settings": serialize_whatsapp_settings(settings_doc, tenant),
        "metaEmbeddedSignup": build_meta_embedded_signup_readiness(),
        "nextStep": "phase_f_register_phone_number",
        "webhookSubscription": {
            "status": "subscribed",
            "wabaId": waba_id,
            "callbackUrl": callback_url,
            "verifyToken": verify_token,
            "providerResponse": provider_response,
        },
    }


async def register_embedded_signup_phone_number(tenant_id: str, payload: WhatsAppPhoneRegistrationRequest, user: dict) -> dict:
    """Phase F: register the connected phone number for WhatsApp Cloud API use."""
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    now = datetime.now(timezone.utc)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Meta WhatsApp connection found for this business.")
    if integration.get("provider") != "meta_cloud":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone registration is available only for Meta Cloud connections.")

    access_token = (integration.get("accessToken") or "").strip()
    if not access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exchange the Meta signup code for a business token before registering the phone number.")
    phone_number_id = (integration.get("phoneNumberId") or "").strip()
    if not phone_number_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meta Phone Number ID is missing. Complete Embedded Signup again.")
    if integration.get("webhookSubscriptionStatus") != "subscribed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscribe WABA webhooks before registering the phone number.")

    api_version = integration.get("apiVersion") or settings.meta_graph_api_version or settings.whatsapp_api_version
    try:
        registration_data = await _post_meta_phone_number_registration(
            phone_number_id=phone_number_id,
            access_token=access_token,
            api_version=api_version,
            pin=payload.pin,
        )
    except HTTPException as exc:
        await db.whatsapp_integrations.update_one(
            {"_id": integration["_id"]},
            {
                "$set": {
                    "phoneRegistrationStatus": "registration_failed",
                    "connectionStatus": "phone_registration_failed",
                    "status": "phone_registration_failed",
                    "lastError": str(exc.detail),
                    "lastErrorAt": now,
                    "updatedAt": now,
                }
            },
        )
        raise

    update_doc = {
        "phoneRegistrationStatus": "registered",
        "phoneRegisteredAt": now,
        "phoneRegistrationResponse": registration_data,
        "connectionStatus": "phone_registered",
        "status": "connected_meta_cloud",
        "isConnected": True,
        "lastError": "",
        "lastErrorAt": None,
        "updatedAt": now,
    }
    await db.whatsapp_integrations.update_one({"_id": integration["_id"]}, {"$set": update_doc, "$unset": {"registrationPin": ""}})
    settings_doc = await db.whatsapp_integrations.find_one({"_id": integration["_id"]})
    return {
        "tenant": serialize_document(tenant),
        "settings": serialize_whatsapp_settings(settings_doc, tenant),
        "metaEmbeddedSignup": build_meta_embedded_signup_readiness(),
        "nextStep": "phase_g_webhook_routing_by_phone_number_id",
        "phoneRegistration": {
            "status": "registered",
            "phoneNumberId": phone_number_id,
            "providerResponse": registration_data,
        },
    }


async def disconnect_whatsapp_settings(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    now = datetime.now(timezone.utc)
    await db.whatsapp_integrations.update_one(
        {"tenantId": tenant_oid},
        {"$set": {"isConnected": False, "status": "disconnected", "updatedAt": now}},
    )
    settings_doc = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    return {"tenant": serialize_document(tenant), "settings": serialize_whatsapp_settings(settings_doc, tenant)}


async def find_whatsapp_integration_for_inbound(*, tenant_id: ObjectId | None = None, phone_number_id: str = "", business_number: str = "") -> tuple[dict, dict]:
    """Resolve a real incoming WhatsApp webhook to the correct tenant.

    Phase G uses Meta's metadata.phone_number_id as the primary routing key.
    That lets many businesses use the same BizXusAI webhook URL while each
    message is routed to the tenant that owns the connected Phone Number ID.
    The display phone number fallback is kept only for older/manual setups.
    """
    db = get_database()
    integration = None
    clean_phone_number_id = str(phone_number_id or "").strip()
    if tenant_id:
        integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_id, "isConnected": True})
    if not integration and clean_phone_number_id:
        integration = await db.whatsapp_integrations.find_one(_phone_id_query(clean_phone_number_id))
    if not integration and business_number:
        integration = await db.whatsapp_integrations.find_one(
            {"normalizedBusinessWhatsAppNumber": normalize_phone(business_number), "isConnected": True}
        )
    if not integration:
        if not (tenant_id or clean_phone_number_id or business_number):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to map WhatsApp message to a business.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No connected WhatsApp integration matched this message.")
    if clean_phone_number_id and integration.get("phoneNumberId") and integration.get("phoneNumberId") != clean_phone_number_id:
        # Never route a webhook to the wrong business when Meta sends a phone number ID.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Incoming WhatsApp Phone Number ID does not match the connected business.")
    tenant = await db.tenants.find_one({"_id": integration["tenantId"], "status": "active"})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected business is not active.")
    if "ai_chat" not in tenant.get("enabledModuleCodes", []) or "whatsapp_agent" not in tenant.get("enabledModuleCodes", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AI Chat and WhatsApp Agent modules must be enabled.")
    return integration, tenant


async def get_or_create_whatsapp_conversation(tenant: dict, customer_phone: str, customer_name: str = "", wa_id: str = "") -> dict:
    db = get_database()
    normalized_phone = normalize_phone(customer_phone)
    now = datetime.now(timezone.utc)
    conversation = await db.conversations.find_one(
        {
            "tenantId": tenant["_id"],
            "channel": "whatsapp",
            "externalCustomerPhone": normalized_phone,
            "status": "open",
        }
    )
    if conversation:
        updates = {"lastMessageAt": now, "updatedAt": now}
        if customer_name and not conversation.get("externalCustomerName"):
            updates["externalCustomerName"] = customer_name
        if wa_id and not conversation.get("waId"):
            updates["waId"] = wa_id
        if len(updates) > 2:
            await db.conversations.update_one({"_id": conversation["_id"]}, {"$set": updates})
            conversation = await db.conversations.find_one({"_id": conversation["_id"]})
        return conversation

    conversation = {
        "tenantId": tenant["_id"],
        "branchId": None,
        "customerId": None,
        "customerUserId": None,
        "channel": "whatsapp",
        "status": "open",
        "externalCustomerPhone": normalized_phone,
        "externalCustomerName": customer_name or "WhatsApp Customer",
        "waId": wa_id or normalized_phone,
        "languageDetected": "english",
        "pendingOrderDraft": {},
        "summary": "",
        "lastIntent": "",
        "lastIntentConfidence": 0.0,
        "lastAssistantSource": "",
        "lastKnowledgeCount": 0,
        "lastMessageAt": now,
        "createdAt": now,
        "updatedAt": now,
    }
    conversation["_id"] = (await db.conversations.insert_one(conversation)).inserted_id
    return conversation


def _needs_handoff(message_text: str, integration: dict) -> bool:
    if not integration.get("handoffEnabled", True):
        return False
    normalized = message_text.lower()
    return any(keyword and keyword in normalized for keyword in integration.get("handoffKeywords", []))


def _whatsapp_text_tokens(message_text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", str(message_text or "").lower()) if token}


CONFIRMATION_WORDS = {
    "yes",
    "y",
    "confirm",
    "confirmed",
    "ok",
    "okay",
    "done",
    "haan",
    "han",
    "ha",
    "g",
    "ji",
    "jee",
    "theek",
    "krdo",
    "kar",
    "do",
}
CANCEL_WORDS = {"cancel", "remove", "delete", "nahi", "nahin", "no", "stop", "chor", "choro"}
DELIVERY_WORDS = {"delivery", "deliver", "home", "ghar", "address", "bhej", "send", "courier"}
PICKUP_WORDS = {"pickup", "pick", "collect", "counter", "shop", "store"}
KNOWN_CITY_ALIASES = {
    "attock": "Attock",
    "wah": "Wah Cantt",
    "wahcantt": "Wah Cantt",
    "taxila": "Taxila",
    "rawalpindi": "Rawalpindi",
    "pindi": "Rawalpindi",
    "islamabad": "Islamabad",
    "lahore": "Lahore",
    "karachi": "Karachi",
    "peshawar": "Peshawar",
    "multan": "Multan",
    "faisalabad": "Faisalabad",
}


def _is_whatsapp_confirmation(message_text: str) -> bool:
    normalized = str(message_text or "").strip().lower()
    tokens = _whatsapp_text_tokens(normalized)
    if normalized in {"g", "ji", "jee", "ok", "okay", "yes", "haan", "han", "ha", "done", "confirm"}:
        return True
    if any(phrase in normalized for phrase in ["confirm kar", "order confirm", "kar do", "krdo", "place order", "final kar"]):
        return True
    return bool(tokens and tokens.issubset(CONFIRMATION_WORDS) and tokens.intersection({"yes", "ok", "okay", "confirm", "haan", "han", "g", "ji", "done"}))


def _is_whatsapp_cancel(message_text: str) -> bool:
    normalized = str(message_text or "").strip().lower()
    tokens = _whatsapp_text_tokens(normalized)
    return bool(tokens.intersection(CANCEL_WORDS) or any(phrase in normalized for phrase in ["cancel order", "draft cancel", "nahi chahiye", "nahin chahiye"]))


def _extract_city_from_text(message_text: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", str(message_text or "").lower())
    compact = normalized.replace(" ", "")
    for alias, city in KNOWN_CITY_ALIASES.items():
        if alias in normalized.split() or alias in compact:
            return city
    city_match = re.search(r"(?:city|shehar|shahar)\s*[:\-]?\s*([a-zA-Z ]{2,40})", message_text or "", re.IGNORECASE)
    if city_match:
        return city_match.group(1).strip().title()
    parts = [part.strip() for part in re.split(r"[,|]", str(message_text or "")) if part.strip()]
    if len(parts) >= 2 and len(parts[-1]) <= 40:
        return parts[-1].title()
    return ""


def _looks_like_address(message_text: str) -> bool:
    lowered = str(message_text or "").lower()
    return bool(
        re.search(r"\b(house|home|street|st\.?|road|rd\.?|sector|phase|mohalla|colony|gali|shop|near|opposite|address)\b", lowered)
        or re.search(r"\b\d{1,5}\b", lowered)
        or "," in lowered
    )


def _extract_fulfillment_from_whatsapp(message_text: str, existing_fulfillment: dict | None = None) -> dict:
    existing = dict(existing_fulfillment or {})
    existing_address = dict(existing.get("address") or {})
    lowered = str(message_text or "").lower()
    tokens = _whatsapp_text_tokens(lowered)
    fulfillment_type = str(existing.get("type") or "none").lower()
    if tokens.intersection(PICKUP_WORDS):
        fulfillment_type = "pickup"
        existing_address = {}
    elif tokens.intersection(DELIVERY_WORDS) or _looks_like_address(message_text):
        fulfillment_type = "delivery"

    if fulfillment_type == "delivery":
        line1 = existing_address.get("line1") or ""
        city = existing_address.get("city") or ""
        extracted_city = _extract_city_from_text(message_text)
        if extracted_city:
            city = extracted_city
        if _looks_like_address(message_text):
            # Keep the full customer text as line1. It is safer than trying to over-parse Roman Urdu addresses.
            line1 = str(message_text or "").strip()[:240]
        return {"type": "delivery", "address": {"line1": line1, "city": city}}
    if fulfillment_type == "pickup":
        return {"type": "pickup", "address": {}}
    return {"type": "none", "address": {}}


def _allowed_fulfillment_types_for_tenant(tenant: dict) -> list[str]:
    rules = (((tenant.get("settings") or {}).get("categoryHints") or {}).get("fulfillment") or {})
    allowed = rules.get("allowedTypes") or ["none"]
    return [str(item).lower() for item in allowed if str(item).strip()]


def _draft_line_to_requested_item(line: dict) -> dict:
    return {
        "itemId": str(line.get("itemId") or ""),
        "quantity": int(line.get("quantity") or 1),
        "selectedVariantIndex": line.get("selectedVariantIndex"),
        "selectedVariantName": line.get("selectedVariantName") or "",
        "selectedOptions": line.get("selectedOptions") or {},
        "variantSku": line.get("variantSku") or "",
    }


def _merge_whatsapp_order_context(draft_order: dict, message_text: str, *, customer_phone: str = "", customer_name: str = "", tenant: dict | None = None) -> dict:
    updated = dict(draft_order or {})
    if not updated.get("items"):
        return updated
    current_fulfillment = updated.get("fulfillment") or {}
    if not current_fulfillment:
        preference = updated.get("fulfillmentPreference") or {}
        preference_type = str(preference.get("type") or "none").lower()
        current_fulfillment = {"type": preference_type if preference_type in {"delivery", "pickup"} else "none", "address": {}}
    updated["fulfillment"] = _extract_fulfillment_from_whatsapp(message_text, current_fulfillment)
    snapshot = dict(updated.get("customerSnapshot") or {})
    if customer_name and customer_name != "WhatsApp Customer":
        snapshot["name"] = customer_name
    snapshot["phone"] = normalize_phone(customer_phone) or snapshot.get("phone", "")
    updated["customerSnapshot"] = snapshot
    updated["source"] = "whatsapp_agent"
    updated["updatedAt"] = datetime.now(timezone.utc)
    return updated


def _draft_missing_fields(draft_order: dict, tenant: dict) -> list[str]:
    missing: list[str] = []
    if not draft_order.get("items"):
        missing.append("item")
    if draft_order.get("canConfirm") is False or draft_order.get("confirmationIssues"):
        missing.extend(draft_order.get("confirmationIssues") or ["stock review"])
    fulfillment = draft_order.get("fulfillment") or {}
    allowed_types = _allowed_fulfillment_types_for_tenant(tenant)
    fulfillment_type = str(fulfillment.get("type") or "none").lower()
    if any(item in allowed_types for item in ["delivery", "pickup"]) and fulfillment_type == "none":
        missing.append("delivery or pickup")
    if fulfillment_type == "delivery":
        address = fulfillment.get("address") or {}
        if not address.get("line1"):
            missing.append("delivery address")
        if not address.get("city"):
            missing.append("city")
    customer = draft_order.get("customerSnapshot") or {}
    if not customer.get("phone"):
        missing.append("customer phone")
    return list(dict.fromkeys(missing))


def _format_whatsapp_draft_followup(draft_order: dict, tenant: dict, language_mode: str) -> str:
    missing = _draft_missing_fields(draft_order, tenant)
    lines = draft_order.get("items") or []
    line_text = "\n".join(
        f"{line.get('quantity', 1)}x {line.get('name', 'Item')}"
        f"{(' - ' + line.get('selectedVariantName')) if line.get('selectedVariantName') else ''}"
        for line in lines[:4]
    )
    total = (draft_order.get("pricing") or {}).get("total", 0)
    currency = (draft_order.get("pricing") or {}).get("currency", "PKR")
    if missing:
        if language_mode in {"roman_urdu", "mixed"}:
            if "delivery or pickup" in missing:
                return f"Draft ready hai:\n{line_text}\nTotal: {currency} {total}\nDelivery chahiye ya pickup?"
            if "delivery address" in missing or "city" in missing:
                return "Delivery ke liye please apna complete address aur city send kar dein.\nExample: House 12, Main Road, Attock"
            return f"Draft complete karne ke liye yeh details chahiye: {', '.join(missing)}."
        if "delivery or pickup" in missing:
            return f"Draft ready:\n{line_text}\nTotal: {currency} {total}\nDelivery or pickup?"
        if "delivery address" in missing or "city" in missing:
            return "For delivery, please send your complete address and city.\nExample: House 12, Main Road, Attock"
        return f"I still need these details before confirming: {', '.join(missing)}."
    if language_mode in {"roman_urdu", "mixed"}:
        return f"Draft ready hai:\n{line_text}\nTotal: {currency} {total}\nConfirm kar doon?"
    return f"Draft ready:\n{line_text}\nTotal: {currency} {total}\nShould I confirm it?"


def _format_whatsapp_transaction_confirmed(transaction: dict, language_mode: str) -> str:
    number = transaction.get("transactionNumber") or "your order"
    total = ((transaction.get("pricing") or {}).get("total") or 0)
    currency = "PKR"
    items = transaction.get("items") or []
    item_text = ", ".join(f"{item.get('quantity', 1)}x {item.get('name', 'Item')}" for item in items[:3])
    if language_mode in {"roman_urdu", "mixed"}:
        return f"✅ Order confirm ho gaya.\nOrder #: {number}\nItems: {item_text}\nTotal: {currency} {total}\nThank you!"
    return f"✅ Your order is confirmed.\nOrder #: {number}\nItems: {item_text}\nTotal: {currency} {total}\nThank you!"


async def _create_whatsapp_transaction_from_draft(tenant: dict, conversation: dict, draft_order: dict, customer_phone: str, customer_name: str) -> dict:
    db = get_database()
    if not draft_order.get("items"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No WhatsApp draft order is available to confirm.")
    fulfillment = normalize_fulfillment(draft_order.get("fulfillment") or {})
    validate_tenant_fulfillment(tenant, fulfillment)
    normalized_custom_fields = await validate_custom_values_for_tenant_oid(tenant["_id"], "transactions", "transaction", draft_order.get("customFields") or {})
    if not normalized_custom_fields["valid"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=normalized_custom_fields["errors"])
    requested_items = [_draft_line_to_requested_item(line) for line in draft_order.get("items") or []]
    resolved_items, transaction_items, subtotal = await resolve_requested_order_items(tenant, requested_items, db)
    requested_transaction_type = normalize_transaction_type(draft_order.get("transactionType") or "auto")
    transaction_type = infer_transaction_type(requested_transaction_type, resolved_items)
    payment_options = await get_customer_payment_options_for_tenant(tenant["_id"])
    payment_preference = normalize_customer_payment_preference(draft_order.get("paymentMethod"), payment_options)
    now = datetime.now(timezone.utc)
    snapshot = draft_order.get("customerSnapshot") or {}
    normalized_phone = normalize_phone(customer_phone) or snapshot.get("phone") or ""
    transaction = {
        "tenantId": tenant["_id"],
        "branchId": None,
        "customerId": None,
        "customerUserId": None,
        "customerProfileId": None,
        "transactionType": transaction_type,
        "transactionNumber": await generate_transaction_number(tenant["_id"], transaction_type),
        "source": "whatsapp",
        "status": get_initial_transaction_status(transaction_type),
        "items": transaction_items,
        "pricing": {"subtotal": subtotal, "discount": 0, "tax": 0, "deliveryFee": 0, "total": subtotal},
        "paymentStatus": get_initial_payment_status(transaction_type),
        "paymentSummary": {"total": subtotal, "paid": 0, "cod": 0, "pending": 0, "rejected": 0, "refunded": 0, "balance": subtotal},
        "paymentPreference": payment_preference,
        "paymentInstructions": payment_options,
        "fulfillment": fulfillment,
        "customerSnapshot": {
            "name": snapshot.get("name") or customer_name or "WhatsApp Customer",
            "phone": normalized_phone,
            "email": "",
        },
        "notes": normalize_notes(draft_order.get("notes") or "Created by WhatsApp AI agent."),
        "internalNotes": f"Created from WhatsApp conversation {conversation.get('_id')}",
        "customFields": normalized_custom_fields["values"],
        "statusHistory": [
            {
                "field": "status",
                "from": None,
                "to": get_initial_transaction_status(transaction_type),
                "note": "Created from WhatsApp AI agent.",
                "changedAt": now,
                "changedByUserId": None,
            }
        ],
        "createdBy": None,
        "createdAt": now,
        "updatedAt": now,
    }
    transaction["_id"] = (await db.transactions.insert_one(transaction)).inserted_id
    try:
        transaction = await reserve_transaction_stock(transaction, None)
    except Exception:
        await db.transactions.delete_one({"_id": transaction["_id"]})
        raise
    customer_id = await sync_customer_stats_for_transaction(tenant, transaction)
    transaction["customerId"] = customer_id
    await db.conversations.update_one(
        {"_id": conversation["_id"]},
        {"$set": {"pendingOrderDraft": {}, "summary": f"WhatsApp order confirmed as {transaction['transactionNumber']}.", "updatedAt": now, "lastMessageAt": now}},
    )
    await create_business_notification(
        tenant["_id"],
        "order_alert",
        f"New WhatsApp {transaction_type.replace('_', ' ')} {transaction['transactionNumber']}",
        f"{transaction['customerSnapshot'].get('name') or 'A WhatsApp customer'} confirmed a new {transaction_type.replace('_', ' ')} via WhatsApp AI agent.",
        priority="high" if transaction_type == "order" else "medium",
        metadata={
            "transactionId": str(transaction["_id"]),
            "transactionNumber": transaction["transactionNumber"],
            "transactionType": transaction_type,
            "source": "whatsapp_agent",
            "conversationId": str(conversation["_id"]),
            "customerPhone": normalized_phone,
            "tenantSlug": tenant.get("slug", ""),
        },
    )
    return transaction


async def _maybe_handle_whatsapp_draft_context(
    *,
    tenant: dict,
    conversation: dict,
    integration: dict,
    message_text: str,
    customer_phone: str,
    customer_name: str,
    language_mode: str,
) -> dict | None:
    draft_order = conversation.get("pendingOrderDraft") or {}
    if not draft_order.get("items"):
        return None
    if _is_whatsapp_cancel(message_text):
        await get_database().conversations.update_one(
            {"_id": conversation["_id"]},
            {"$set": {"pendingOrderDraft": {}, "summary": "WhatsApp draft cancelled.", "updatedAt": datetime.now(timezone.utc)}},
        )
        reply = "Draft cancel kar diya gaya hai." if language_mode in {"roman_urdu", "mixed"} else "I cancelled the draft order."
        return {"reply": reply, "draftOrder": {}, "transaction": None, "metaIntent": "whatsapp_draft_cancelled", "toolCalls": [{"tool": "whatsapp_draft_context", "action": "cancelled"}]}

    tokens = _whatsapp_text_tokens(message_text)
    is_context_detail = bool(tokens.intersection(DELIVERY_WORDS | PICKUP_WORDS) or _looks_like_address(message_text) or _is_whatsapp_confirmation(message_text))
    if not is_context_detail:
        # Let the main agent handle new product/order questions instead of trapping
        # the customer in an older pending draft.
        return None

    updated_draft = _merge_whatsapp_order_context(
        draft_order,
        message_text,
        customer_phone=customer_phone,
        customer_name=customer_name,
        tenant=tenant,
    )
    missing = _draft_missing_fields(updated_draft, tenant)
    confirm_requested = _is_whatsapp_confirmation(message_text)

    # If the customer only sent pickup/delivery/address details, preserve the draft and ask the next needed step.
    if not confirm_requested:
        await get_database().conversations.update_one(
            {"_id": conversation["_id"]},
            {"$set": {"pendingOrderDraft": updated_draft, "updatedAt": datetime.now(timezone.utc)}},
        )
        return {
            "reply": _format_whatsapp_draft_followup(updated_draft, tenant, language_mode),
            "draftOrder": updated_draft,
            "transaction": None,
            "metaIntent": "whatsapp_draft_context_updated",
            "toolCalls": [{"tool": "whatsapp_draft_context", "action": "updated", "missing": missing}],
        }

    if missing:
        await get_database().conversations.update_one(
            {"_id": conversation["_id"]},
            {"$set": {"pendingOrderDraft": updated_draft, "updatedAt": datetime.now(timezone.utc)}},
        )
        return {
            "reply": _format_whatsapp_draft_followup(updated_draft, tenant, language_mode),
            "draftOrder": updated_draft,
            "transaction": None,
            "metaIntent": "whatsapp_draft_needs_details",
            "toolCalls": [{"tool": "whatsapp_draft_context", "action": "needs_details", "missing": missing}],
        }

    try:
        transaction = await _create_whatsapp_transaction_from_draft(tenant, conversation, updated_draft, customer_phone, customer_name)
    except HTTPException as exc:
        await get_database().conversations.update_one(
            {"_id": conversation["_id"]},
            {"$set": {"pendingOrderDraft": updated_draft, "updatedAt": datetime.now(timezone.utc)}},
        )
        return {
            "reply": f"Order confirm nahi ho saka: {exc.detail}",
            "draftOrder": updated_draft,
            "transaction": None,
            "metaIntent": "whatsapp_draft_confirmation_failed",
            "toolCalls": [{"tool": "whatsapp_order_confirmation", "action": "failed", "error": str(exc.detail)}],
        }

    return {
        "reply": _format_whatsapp_transaction_confirmed(transaction, language_mode),
        "draftOrder": {},
        "transaction": serialize_document(transaction),
        "metaIntent": "whatsapp_order_confirmed",
        "toolCalls": [{"tool": "whatsapp_order_confirmation", "action": "confirmed", "transactionId": str(transaction["_id"]), "transactionNumber": transaction.get("transactionNumber", "")}],
    }


async def _log_inbound_message(
    *,
    tenant_id: ObjectId,
    conversation_id: ObjectId | None,
    customer_phone: str,
    message_text: str,
    provider: str,
    provider_message_id: str = "",
    raw_payload: dict | None = None,
) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    log = {
        "tenantId": tenant_id,
        "conversationId": conversation_id,
        "provider": provider,
        "direction": "inbound",
        "fromPhone": customer_phone,
        "messageText": message_text,
        "providerMessageId": provider_message_id,
        "deliveryStatus": "received",
        "rawPayload": raw_payload or {},
        "createdAt": now,
        "updatedAt": now,
    }
    log["_id"] = (await db.whatsapp_message_logs.insert_one(log)).inserted_id
    return log


async def _create_whatsapp_owner_notification(
    tenant_id: ObjectId,
    notification_type: str,
    title: str,
    message: str,
    *,
    priority: str = "medium",
    metadata: dict | None = None,
    source_key: str | None = None,
) -> None:
    try:
        await create_business_notification(
            tenant_id,
            notification_type,
            title,
            message,
            priority=priority,
            metadata=metadata or {},
            source_key=source_key,
        )
    except Exception:
        # WhatsApp webhooks must not fail just because owner notification delivery/storage failed.
        return


async def process_whatsapp_inbound(
    *,
    integration: dict,
    tenant: dict,
    customer_phone: str,
    message_text: str,
    customer_name: str = "",
    provider_message_id: str = "",
    raw_payload: dict | None = None,
) -> dict:
    db = get_database()
    if not message_text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WhatsApp message text is empty.")

    await ensure_tenant_module_usage_available(tenant["_id"], "ai_chat")
    await ensure_tenant_module_usage_available(tenant["_id"], "whatsapp_agent")
    conversation = await get_or_create_whatsapp_conversation(tenant, customer_phone, customer_name, wa_id=customer_phone)
    if provider_message_id:
        existing_log = await db.whatsapp_message_logs.find_one(
            {
                "tenantId": tenant["_id"],
                "direction": "inbound",
                "providerMessageId": provider_message_id,
            }
        )
        if existing_log:
            messages = await load_conversation_messages(conversation["_id"])
            return {
                "tenant": serialize_document(tenant),
                "settings": serialize_whatsapp_settings(integration, tenant),
                "conversation": serialize_document(conversation),
                "messages": messages,
                "reply": "",
                "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
                "outboundLog": None,
                "outboundError": "",
                "duplicate": True,
                "handoffRequired": conversation.get("status") == "handoff",
                "confirmedTransaction": None,
            }
    await _log_inbound_message(
        tenant_id=tenant["_id"],
        conversation_id=conversation["_id"],
        customer_phone=customer_phone,
        message_text=message_text,
        provider=integration.get("provider", "mock"),
        provider_message_id=provider_message_id,
        raw_payload=raw_payload,
    )

    language_mode = detect_language_mode(message_text)
    await save_message(conversation, tenant["_id"], "customer", message_text, intent="whatsapp_inbound", confidence=1.0)
    recent_messages = await load_conversation_messages(conversation["_id"])
    confirmed_transaction = None

    if _needs_handoff(message_text, integration):
        ai_text = HANDOFF_REPLY
        draft_order = {}
        rag_sources = []
        tool_calls = [{"tool": "handoff_detector", "handoffRequested": True}]
        reply_meta = {
            "intent": "handoff_requested",
            "confidence": 1.0,
            "responseSource": "handoff_rule",
            "knowledgeCount": 0,
            "localizationScore": 1.0,
        }
        await db.conversations.update_one({"_id": conversation["_id"]}, {"$set": {"status": "handoff", "handoffRequestedAt": datetime.now(timezone.utc)}})
        await _create_whatsapp_owner_notification(
            tenant["_id"],
            "whatsapp_handoff",
            "WhatsApp handoff requested",
            f"{customer_name or normalize_phone(customer_phone)} asked for a human reply on WhatsApp.",
            priority="high",
            metadata={
                "conversationId": str(conversation["_id"]),
                "customerPhone": normalize_phone(customer_phone),
                "messageText": message_text,
            },
            source_key=f"whatsapp_handoff:{conversation['_id']}",
        )
    elif not integration.get("agentEnabled", True):
        ai_text = integration.get("fallbackReply") or "Your WhatsApp message has been received. The business team will reply soon."
        draft_order = {}
        rag_sources = []
        tool_calls = [{"tool": "agent_gate", "agentEnabled": False}]
        reply_meta = {
            "intent": "agent_disabled",
            "confidence": 1.0,
            "responseSource": "agent_disabled_rule",
            "knowledgeCount": 0,
            "localizationScore": 1.0,
        }
    elif integration.get("autoReplyEnabled", True):
        contextual_result = await _maybe_handle_whatsapp_draft_context(
            tenant=tenant,
            conversation=conversation,
            integration=integration,
            message_text=message_text,
            customer_phone=customer_phone,
            customer_name=customer_name,
            language_mode=language_mode,
        )
        if contextual_result:
            ai_text = contextual_result["reply"]
            draft_order = contextual_result.get("draftOrder") or {}
            confirmed_transaction = contextual_result.get("transaction")
            rag_sources = []
            tool_calls = contextual_result.get("toolCalls") or []
            reply_meta = {
                "intent": contextual_result.get("metaIntent") or "whatsapp_context",
                "confidence": 1.0,
                "responseSource": "whatsapp_context_manager",
                "knowledgeCount": 0,
                "localizationScore": 1.0,
            }
        else:
            try:
                ai_text, draft_order, rag_sources, tool_calls, reply_meta = await build_ai_reply(tenant, message_text, recent_messages, channel="whatsapp")
                # Preserve an existing WhatsApp draft when the customer sends delivery/pickup/address details.
                if not draft_order.get("items") and (conversation.get("pendingOrderDraft") or {}).get("items"):
                    draft_order = _merge_whatsapp_order_context(
                        conversation.get("pendingOrderDraft") or {},
                        message_text,
                        customer_phone=customer_phone,
                        customer_name=customer_name,
                        tenant=tenant,
                    )
                    ai_text = _format_whatsapp_draft_followup(draft_order, tenant, language_mode)
                    tool_calls = [*tool_calls, {"tool": "whatsapp_draft_context", "action": "preserved_existing_draft"}]
                    reply_meta = {**reply_meta, "intent": "whatsapp_draft_context_updated", "responseSource": "whatsapp_context_manager"}
            except Exception as exc:
                ai_text = integration.get("fallbackReply") or DEFAULT_FALLBACK_REPLY
                draft_order = {}
                rag_sources = []
                tool_calls = [{"tool": "agent_error_guard", "error": type(exc).__name__}]
                reply_meta = {
                    "intent": "agent_error",
                    "confidence": 1.0,
                    "responseSource": "agent_error_guard",
                    "knowledgeCount": 0,
                    "localizationScore": 0,
                }
                await _create_whatsapp_owner_notification(
                    tenant["_id"],
                    "whatsapp_agent_error",
                    "WhatsApp AI needs review",
                    f"The WhatsApp agent could not answer {customer_name or normalize_phone(customer_phone)} automatically.",
                    priority="high",
                    metadata={
                        "conversationId": str(conversation["_id"]),
                        "customerPhone": normalize_phone(customer_phone),
                        "messageText": message_text,
                        "errorType": type(exc).__name__,
                        "error": str(exc)[:500],
                    },
                )
    else:
        ai_text = integration.get("welcomeMessage") or "Your message has been received. The business team will reply soon."
        draft_order = {}
        rag_sources = []
        tool_calls = [{"tool": "auto_reply_gate", "autoReplyEnabled": False}]
        reply_meta = {
            "intent": "manual_review",
            "confidence": 1.0,
            "responseSource": "manual_review_rule",
            "knowledgeCount": 0,
            "localizationScore": 1.0,
        }

    now = datetime.now(timezone.utc)
    await db.conversations.update_one(
        {"_id": conversation["_id"]},
        {
            "$set": {
                "languageDetected": language_mode,
                "pendingOrderDraft": draft_order,
                "summary": ai_text,
                "lastIntent": reply_meta["intent"],
                "lastIntentConfidence": reply_meta["confidence"],
                "lastAssistantSource": reply_meta["responseSource"],
                "lastKnowledgeCount": reply_meta["knowledgeCount"],
                "lastLocalizationScore": reply_meta.get("localizationScore", 0),
                "lastMessageAt": now,
                "updatedAt": now,
            }
        },
    )
    conversation = await db.conversations.find_one({"_id": conversation["_id"]})
    await save_message(
        conversation,
        tenant["_id"],
        "ai",
        ai_text,
        intent=reply_meta["intent"],
        confidence=reply_meta["confidence"],
        rag_sources=rag_sources,
        tool_calls=tool_calls,
    )

    outbound_log = None
    outbound_error = ""
    if integration.get("autoReplyEnabled", True):
        try:
            outbound_log = await send_whatsapp_text(
                tenant_id=tenant["_id"],
                conversation_id=conversation["_id"],
                provider=integration.get("provider", "mock"),
                to_phone=normalize_phone(customer_phone),
                message_text=ai_text,
                integration=integration,
                raw_context={"source": "whatsapp_agent_auto_reply"},
            )
            await db.whatsapp_integrations.update_one(
                {"_id": integration["_id"]},
                {"$set": {"lastInboundAt": now, "lastOutboundAt": now, "updatedAt": now}},
            )
        except WhatsAppSendError as exc:
            outbound_error = str(exc)
            await db.whatsapp_integrations.update_one(
                {"_id": integration["_id"]},
                {"$set": {"lastInboundAt": now, "lastError": outbound_error, "updatedAt": now}},
            )
    else:
        await db.whatsapp_integrations.update_one({"_id": integration["_id"]}, {"$set": {"lastInboundAt": now, "updatedAt": now}})

    messages = await load_conversation_messages(conversation["_id"])
    return {
        "tenant": serialize_document(tenant),
        "settings": serialize_whatsapp_settings(integration, tenant),
        "conversation": serialize_document(conversation),
        "messages": messages,
        "reply": ai_text,
        "draftOrder": serialize_document(conversation.get("pendingOrderDraft")) or {},
        "outboundLog": serialize_document(outbound_log) if outbound_log else None,
        "outboundError": outbound_error,
        "duplicate": False,
        "handoffRequired": conversation.get("status") == "handoff",
        "confirmedTransaction": confirmed_transaction,
    }


async def simulate_whatsapp_inbound(tenant_id: str, payload: WhatsAppMockInboundRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid, "isConnected": True})
    if not integration:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connect WhatsApp before testing inbound messages.")
    return await process_whatsapp_inbound(
        integration=integration,
        tenant=tenant,
        customer_phone=payload.customerPhone,
        customer_name=payload.customerName,
        message_text=payload.messageText,
        provider_message_id=payload.providerMessageId or f"mock-in-{int(datetime.now(timezone.utc).timestamp())}",
        raw_payload={"mock": True, "source": "dashboard_simulator"},
    )


async def send_owner_whatsapp_test(tenant_id: str, payload: WhatsAppOutboundRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid, "isConnected": True})
    if not integration:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connect WhatsApp before sending a test message.")
    try:
        log = await send_whatsapp_text(
            tenant_id=tenant_oid,
            provider=integration.get("provider", "mock"),
            to_phone=normalize_phone(payload.toPhone),
            message_text=payload.messageText,
            integration=integration,
            raw_context={"source": "owner_test_message"},
        )
    except WhatsAppSendError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unable to send WhatsApp test: {exc}") from exc
    return {"tenant": serialize_document(tenant), "log": serialize_document(log)}


async def list_whatsapp_conversations(tenant_id: str, user: dict, page: int = 1, limit: int = 20) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    query = {"tenantId": tenant_oid, "channel": "whatsapp"}
    total = await db.conversations.count_documents(query)
    cursor = db.conversations.find(query).sort("lastMessageAt", -1).skip((page - 1) * limit).limit(limit)
    items = [serialize_document(conversation) async for conversation in cursor]
    return {
        "tenant": serialize_document(tenant),
        "items": items,
        "pagination": {"page": page, "limit": limit, "total": total, "totalPages": (total + limit - 1) // limit},
    }


async def verify_whatsapp_webhook(mode: str | None, verify_token: str | None, challenge: str | None) -> str:
    if mode != "subscribe" or not verify_token or challenge is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WhatsApp webhook verification request.")
    if verify_token == settings.whatsapp_verify_token:
        return str(challenge)
    db = get_database()
    token_matches_integration = await db.whatsapp_integrations.find_one({"webhookVerifyToken": verify_token, "isConnected": True})
    if token_matches_integration:
        return str(challenge)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid WhatsApp verify token.")


def _extract_text_from_meta_message(message: dict) -> str:
    message_type = message.get("type")
    if message_type == "text":
        return ((message.get("text") or {}).get("body") or "").strip()
    if message_type == "button":
        return ((message.get("button") or {}).get("text") or "").strip()
    if message_type == "interactive":
        interactive = message.get("interactive") or {}
        if interactive.get("type") == "button_reply":
            return ((interactive.get("button_reply") or {}).get("title") or "").strip()
        if interactive.get("type") == "list_reply":
            return ((interactive.get("list_reply") or {}).get("title") or "").strip()
    if message_type in {"image", "document", "audio", "voice", "video", "sticker", "location"}:
        return ""
    return ""


def _extract_meta_whatsapp_message_events(payload: dict) -> list[dict]:
    """Flatten a Meta WhatsApp webhook payload into message routing events.

    Each event keeps the exact phone_number_id from metadata. This is the
    Phase G routing key for multi-business webhooks.
    """
    events: list[dict] = []
    entries = payload.get("entry") or []
    for entry_index, entry in enumerate(entries):
        for change_index, change in enumerate(entry.get("changes") or []):
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "").strip()
            display_phone_number = str(metadata.get("display_phone_number") or "").strip()
            contacts_by_wa_id = {
                str(contact.get("wa_id") or contact.get("input") or ""): contact for contact in value.get("contacts") or []
            }
            for message_index, message in enumerate(value.get("messages") or []):
                from_phone = str(message.get("from") or "").strip()
                contact = contacts_by_wa_id.get(from_phone) or {}
                customer_name = ((contact.get("profile") or {}).get("name") or "WhatsApp Customer").strip()
                text = _extract_text_from_meta_message(message)
                events.append(
                    {
                        "entryIndex": entry_index,
                        "changeIndex": change_index,
                        "messageIndex": message_index,
                        "phoneNumberId": phone_number_id,
                        "displayPhoneNumber": display_phone_number,
                        "fromPhone": from_phone,
                        "customerName": customer_name,
                        "messageText": text,
                        "messageType": message.get("type") or "unknown",
                        "providerMessageId": str(message.get("id") or ""),
                        "timestamp": str(message.get("timestamp") or ""),
                        "raw": {"entry": entry, "change": change, "message": message},
                    }
                )
    return events


def _extract_meta_whatsapp_status_events(payload: dict) -> list[dict]:
    events: list[dict] = []
    for entry_index, entry in enumerate(payload.get("entry") or []):
        for change_index, change in enumerate(entry.get("changes") or []):
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "").strip()
            display_phone_number = str(metadata.get("display_phone_number") or "").strip()
            for status_index, status_payload in enumerate(value.get("statuses") or []):
                events.append(
                    {
                        "entryIndex": entry_index,
                        "changeIndex": change_index,
                        "statusIndex": status_index,
                        "phoneNumberId": phone_number_id,
                        "displayPhoneNumber": display_phone_number,
                        "providerMessageId": str(status_payload.get("id") or ""),
                        "recipientId": str(status_payload.get("recipient_id") or ""),
                        "status": str(status_payload.get("status") or ""),
                        "timestamp": str(status_payload.get("timestamp") or ""),
                        "errors": status_payload.get("errors") or [],
                        "raw": {"entry": entry, "change": change, "status": status_payload},
                    }
                )
    return events


async def _log_whatsapp_routing_event(*, event_type: str, phone_number_id: str = "", tenant_id: ObjectId | None = None, status_text: str = "", detail: str = "", raw_payload: dict | None = None) -> None:
    now = datetime.now(timezone.utc)
    try:
        db = get_database()
        await db.whatsapp_routing_events.insert_one(
            {
                "tenantId": tenant_id,
                "eventType": event_type,
                "phoneNumberId": phone_number_id,
                "status": status_text,
                "detail": detail[:1000],
                "rawPayload": raw_payload or {},
                "createdAt": now,
                "updatedAt": now,
            }
        )
    except Exception:
        logger.debug("Unable to persist WhatsApp routing event", exc_info=True)


async def _process_meta_status_event(event: dict) -> dict:
    db = get_database()
    phone_number_id = event.get("phoneNumberId", "")
    provider_message_id = event.get("providerMessageId", "")
    status_text = event.get("status", "")
    now = datetime.now(timezone.utc)
    integration = None
    tenant_id = None
    if phone_number_id:
        integration = await db.whatsapp_integrations.find_one(_phone_id_query(phone_number_id))
        if integration:
            tenant_id = integration.get("tenantId")
            await db.whatsapp_integrations.update_one(
                {"_id": integration["_id"]},
                {
                    "$set": {
                        "lastWebhookReceivedAt": now,
                        "lastWebhookPhoneNumberId": phone_number_id,
                        "webhookRoutingStatus": "active",
                        "updatedAt": now,
                    }
                },
            )
    update_result = None
    if provider_message_id:
        update_result = await db.whatsapp_message_logs.update_many(
            {"providerMessageId": provider_message_id},
            {
                "$set": {
                    "providerStatus": status_text,
                    "providerStatusPayload": event.get("raw", {}).get("status", {}),
                    "providerStatusAt": now,
                    "updatedAt": now,
                }
            },
        )
    await _log_whatsapp_routing_event(
        event_type="status",
        phone_number_id=phone_number_id,
        tenant_id=tenant_id,
        status_text=status_text or "received",
        detail=f"Provider message {provider_message_id} status {status_text}",
        raw_payload=event.get("raw"),
    )
    return {
        "phoneNumberId": phone_number_id,
        "providerMessageId": provider_message_id,
        "status": status_text,
        "tenantId": str(tenant_id) if tenant_id else "",
        "matchedLogs": getattr(update_result, "modified_count", 0) if update_result is not None else 0,
    }


async def get_whatsapp_webhook_routing_status(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    settings_doc = serialize_whatsapp_settings(integration, tenant)
    routing_ready = bool(
        integration
        and integration.get("provider") == "meta_cloud"
        and integration.get("phoneNumberId")
        and integration.get("webhookSubscriptionStatus") == "subscribed"
        and integration.get("phoneRegistrationStatus") == "registered"
        and integration.get("isConnected")
    )
    recent_events_cursor = db.whatsapp_routing_events.find({"tenantId": tenant_oid}).sort("createdAt", -1).limit(10)
    recent_events = [serialize_document(event) async for event in recent_events_cursor]
    unmatched_recent = await db.whatsapp_routing_events.count_documents({"tenantId": None, "eventType": "unmatched_message"})
    live_agent_ready = bool(routing_ready and integration.get("agentEnabled", True) and integration.get("autoReplyEnabled", True)) if integration else False
    return {
        "tenant": serialize_document(tenant),
        "settings": settings_doc,
        "routing": {
            "ready": routing_ready,
            "liveAgentReady": live_agent_ready,
            "phaseHCapabilities": {
                "routesIncomingByPhoneNumberId": routing_ready,
                "usesTenantRagCatalogAndOrderAgent": live_agent_ready,
                "canCreateWhatsappDraftOrders": live_agent_ready,
                "canConfirmWhatsappOrders": live_agent_ready,
                "savesTransactionsAndReservesStock": live_agent_ready,
            },
            "status": integration.get("webhookRoutingStatus") if integration else "not_configured",
            "phoneNumberId": integration.get("phoneNumberId", "") if integration else "",
            "wabaId": integration.get("wabaId") or integration.get("whatsappBusinessAccountId", "") if integration else "",
            "webhookCallbackUrl": integration.get("webhookCallbackUrl") or _public_webhook_callback_url() if integration else _public_webhook_callback_url(),
            "lastWebhookReceivedAt": integration.get("lastWebhookReceivedAt") if integration else None,
            "lastWebhookPhoneNumberId": integration.get("lastWebhookPhoneNumberId", "") if integration else "",
            "lastRoutingTestAt": integration.get("lastRoutingTestAt") if integration else None,
            "missing": [
                label
                for label, ok in [
                    ("Meta provider", bool(integration and integration.get("provider") == "meta_cloud")),
                    ("Phone Number ID", bool(integration and integration.get("phoneNumberId"))),
                    ("Webhook subscribed", bool(integration and integration.get("webhookSubscriptionStatus") == "subscribed")),
                    ("Phone registered", bool(integration and integration.get("phoneRegistrationStatus") == "registered")),
                    ("Connected", bool(integration and integration.get("isConnected"))),
                ]
                if not ok
            ],
            "recentEvents": recent_events,
            "unmatchedRecentCount": unmatched_recent,
        },
    }


async def test_whatsapp_webhook_routing_for_owner(tenant_id: str, payload: WhatsAppWebhookRoutingTestRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid, "isConnected": True})
    if not integration:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connect Meta WhatsApp before testing webhook routing.")
    if integration.get("provider") != "meta_cloud":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phase G routing test requires a Meta Cloud connection.")
    phone_number_id = (payload.phoneNumberId or integration.get("phoneNumberId") or "").strip()
    if not phone_number_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone Number ID is missing for this business.")
    routed_integration, routed_tenant = await find_whatsapp_integration_for_inbound(phone_number_id=phone_number_id)
    if routed_tenant["_id"] != tenant_oid:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone Number ID routed to a different business.")
    now = datetime.now(timezone.utc)
    await db.whatsapp_integrations.update_one(
        {"_id": integration["_id"]},
        {
            "$set": {
                "webhookRoutingStatus": "active",
                "lastRoutingTestAt": now,
                "lastWebhookPhoneNumberId": phone_number_id,
                "updatedAt": now,
            }
        },
    )
    await _log_whatsapp_routing_event(
        event_type="routing_test",
        phone_number_id=phone_number_id,
        tenant_id=tenant_oid,
        status_text="matched",
        detail="Phone Number ID resolves to this business.",
        raw_payload={"sendReply": payload.sendReply, "customerPhone": payload.customerPhone},
    )
    processed = None
    if payload.sendReply and payload.messageText.strip():
        processed = await process_whatsapp_inbound(
            integration=routed_integration,
            tenant=routed_tenant,
            customer_phone=payload.customerPhone,
            customer_name=payload.customerName,
            message_text=payload.messageText,
            provider_message_id=payload.providerMessageId or f"phase-g-test-{int(now.timestamp())}",
            raw_payload={"phaseGTest": True, "phoneNumberId": phone_number_id},
        )
    settings_doc = await db.whatsapp_integrations.find_one({"_id": integration["_id"]})
    return {
        "tenant": serialize_document(tenant),
        "settings": serialize_whatsapp_settings(settings_doc, tenant),
        "routing": {
            "status": "matched",
            "phoneNumberId": phone_number_id,
            "matchedTenantId": str(routed_tenant["_id"]),
            "matchedBusinessName": routed_tenant.get("name", ""),
            "sentAgentReply": bool(processed),
        },
        "processed": processed or {},
    }


async def process_whatsapp_webhook_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid WhatsApp webhook payload.")
    db = None
    processed: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    statuses: list[dict] = []
    status_events = _extract_meta_whatsapp_status_events(payload)
    for status_event in status_events:
        try:
            statuses.append(await _process_meta_status_event(status_event))
        except Exception as exc:
            errors.append(
                {
                    "type": "status_event_error",
                    "phoneNumberId": status_event.get("phoneNumberId", ""),
                    "providerMessageId": status_event.get("providerMessageId", ""),
                    "detail": str(exc),
                }
            )
    for event in _extract_meta_whatsapp_message_events(payload):
        phone_number_id = event.get("phoneNumberId", "")
        provider_message_id = event.get("providerMessageId", "")
        if not event.get("messageText"):
            skipped.append(
                {
                    "reason": "unsupported_or_empty_message",
                    "phoneNumberId": phone_number_id,
                    "providerMessageId": provider_message_id,
                    "messageType": event.get("messageType", "unknown"),
                }
            )
            await _log_whatsapp_routing_event(
                event_type="skipped_message",
                phone_number_id=phone_number_id,
                status_text="skipped",
                detail=f"Unsupported or empty message type: {event.get('messageType', 'unknown')}",
                raw_payload=event.get("raw"),
            )
            continue
        try:
            integration, tenant = await find_whatsapp_integration_for_inbound(
                phone_number_id=phone_number_id,
                business_number=event.get("displayPhoneNumber", ""),
            )
        except HTTPException as exc:
            error_payload = {
                "type": "routing_error",
                "phoneNumberId": phone_number_id,
                "businessNumber": event.get("displayPhoneNumber", ""),
                "providerMessageId": provider_message_id,
                "statusCode": exc.status_code,
                "detail": str(exc.detail),
            }
            errors.append(error_payload)
            await _log_whatsapp_routing_event(
                event_type="unmatched_message",
                phone_number_id=phone_number_id,
                status_text="error",
                detail=str(exc.detail),
                raw_payload=event.get("raw"),
            )
            continue
        try:
            result = await process_whatsapp_inbound(
                integration=integration,
                tenant=tenant,
                customer_phone=event.get("fromPhone", ""),
                customer_name=event.get("customerName", "WhatsApp Customer"),
                message_text=event.get("messageText", ""),
                provider_message_id=provider_message_id,
                raw_payload=event.get("raw"),
            )
            now = datetime.now(timezone.utc)
            if db is None:
                try:
                    db = get_database()
                except RuntimeError:
                    db = None
            if db is not None:
                await db.whatsapp_integrations.update_one(
                    {"_id": integration["_id"]},
                    {
                        "$set": {
                            "lastWebhookReceivedAt": now,
                            "lastWebhookPhoneNumberId": phone_number_id,
                            "webhookRoutingStatus": "active",
                            "updatedAt": now,
                        }
                    },
                )
            await _log_whatsapp_routing_event(
                event_type="message_routed",
                phone_number_id=phone_number_id,
                tenant_id=tenant["_id"],
                status_text="processed",
                detail=f"Message {provider_message_id} routed to {tenant.get('name', '')}.",
                raw_payload={"providerMessageId": provider_message_id, "fromPhone": event.get("fromPhone", "")},
            )
            processed.append(
                {
                    "tenantId": result["tenant"]["id"],
                    "conversationId": result["conversation"]["id"],
                    "businessName": result["tenant"].get("name", ""),
                    "phoneNumberId": phone_number_id,
                    "customerPhone": normalize_phone(event.get("fromPhone", "")),
                    "reply": result["reply"],
                    "duplicate": result.get("duplicate", False),
                    "outboundError": result.get("outboundError", ""),
                }
            )
        except Exception as exc:
            logger.exception("WhatsApp webhook event processing failed: phone_number_id=%s provider_message_id=%s", phone_number_id, provider_message_id)
            errors.append(
                {
                    "type": "processing_error",
                    "phoneNumberId": phone_number_id,
                    "providerMessageId": provider_message_id,
                    "detail": str(exc),
                }
            )
            await _log_whatsapp_routing_event(
                event_type="processing_error",
                phone_number_id=phone_number_id,
                tenant_id=tenant.get("_id") if isinstance(tenant, dict) else None,
                status_text="error",
                detail=str(exc),
                raw_payload=event.get("raw"),
            )
    return {
        "processedCount": len(processed),
        "skippedCount": len(skipped),
        "errorCount": len(errors),
        "statusCount": len(statuses),
        "items": processed,
        "skipped": skipped,
        "errors": errors,
        "statuses": statuses,
    }




def _phase_i_check(code: str, label: str, passed: bool, detail: str, fix: str = "", severity: str = "required") -> dict:
    return {
        "code": code,
        "label": label,
        "status": "pass" if passed else ("warn" if severity == "warning" else "fail"),
        "detail": detail,
        "fix": fix,
        "severity": severity,
    }


def _safe_created_at(document: dict) -> datetime:
    value = document.get("createdAt") or document.get("updatedAt")
    return value if isinstance(value, datetime) else datetime.min.replace(tzinfo=timezone.utc)


async def get_whatsapp_live_diagnostics(tenant_id: str, user: dict) -> dict:
    """Return a dashboard-friendly Meta WhatsApp troubleshooting report.

    This is intentionally safe for owners: credentials are masked and only readiness,
    URLs, recent logs, and actionable fixes are returned.
    """
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    safe_settings = serialize_whatsapp_settings(integration, tenant)
    webhook_url = (integration or {}).get("webhookCallbackUrl") or _public_webhook_callback_url()
    callback_url = build_meta_embedded_signup_readiness().get("frontendCallbackUrl", "")
    has_token = bool((integration or {}).get("accessToken") or settings.whatsapp_access_token)
    is_meta = bool(integration and integration.get("provider") == "meta_cloud")
    public_https = bool(webhook_url and webhook_url.startswith("https://"))
    recent_logs_cursor = db.whatsapp_message_logs.find({"tenantId": tenant_oid}).sort("createdAt", -1).limit(12)
    recent_logs = [serialize_document(log) async for log in recent_logs_cursor]
    recent_events_cursor = db.whatsapp_routing_events.find({"tenantId": tenant_oid}).sort("createdAt", -1).limit(12)
    recent_events = [serialize_document(event) async for event in recent_events_cursor]
    recent_conversations_cursor = db.conversations.find({"tenantId": tenant_oid, "channel": "whatsapp"}).sort("lastMessageAt", -1).limit(8)
    recent_conversations = [serialize_document(conversation) async for conversation in recent_conversations_cursor]
    last_inbound = next((log for log in recent_logs if log.get("direction") == "inbound"), None)
    last_outbound = next((log for log in recent_logs if log.get("direction") == "outbound"), None)
    failed_logs = [log for log in recent_logs if log.get("deliveryStatus") == "failed" or log.get("providerStatus") == "failed"]
    checklist = [
        _phase_i_check("provider", "Meta Cloud provider selected", is_meta, f"Current provider: {(integration or {}).get('provider', 'not configured')}", "Set provider to Meta Cloud API after Embedded Signup."),
        _phase_i_check("waba", "WABA ID saved", bool((integration or {}).get("wabaId") or (integration or {}).get("whatsappBusinessAccountId")), f"WABA: {(integration or {}).get('wabaId') or (integration or {}).get('whatsappBusinessAccountId') or 'missing'}", "Complete Embedded Signup and token exchange."),
        _phase_i_check("phone_number_id", "Phone Number ID saved", bool((integration or {}).get("phoneNumberId")), f"Phone Number ID: {(integration or {}).get('phoneNumberId') or 'missing'}", "Complete Embedded Signup or add the Meta Phone Number ID."),
        _phase_i_check("token", "Business access token present", has_token, "Token is stored/masked." if has_token else "Token missing.", "Run token exchange after Embedded Signup."),
        _phase_i_check("webhook_https", "Public HTTPS webhook URL", public_https, webhook_url or "BACKEND_PUBLIC_URL missing", "Use ngrok or deployed backend and set BACKEND_PUBLIC_URL."),
        _phase_i_check("webhook_subscription", "WABA webhooks subscribed", bool((integration or {}).get("webhookSubscriptionStatus") == "subscribed"), f"Status: {(integration or {}).get('webhookSubscriptionStatus') or 'pending'}", "Run Phase E subscribe webhooks."),
        _phase_i_check("phone_registered", "Phone registered for Cloud API", bool((integration or {}).get("phoneRegistrationStatus") == "registered"), f"Status: {(integration or {}).get('phoneRegistrationStatus') or 'pending'}", "Run Phase F phone registration with the 6-digit PIN."),
        _phase_i_check("routing", "Webhook routing active", bool((integration or {}).get("webhookRoutingStatus") == "active" or (integration or {}).get("lastWebhookReceivedAt")), f"Status: {(integration or {}).get('webhookRoutingStatus') or 'not tested'}", "Run Phase G routing test or send a real WhatsApp message."),
        _phase_i_check("agent", "Agent enabled", bool((integration or {}).get("agentEnabled", True)), "Agent is enabled." if (integration or {}).get("agentEnabled", True) else "Agent is paused.", "Enable Agent in WhatsApp settings."),
        _phase_i_check("auto_reply", "Auto reply enabled", bool((integration or {}).get("autoReplyEnabled", True)), "Auto reply is enabled." if (integration or {}).get("autoReplyEnabled", True) else "Auto reply is off.", "Turn on Auto Reply in WhatsApp settings."),
        _phase_i_check("recent_inbound", "Recent inbound message", bool(last_inbound), f"Last inbound: {last_inbound.get('fromPhone') if last_inbound else 'none'}", "Send a mock/live customer message." , severity="warning"),
        _phase_i_check("recent_outbound", "Recent outbound reply", bool(last_outbound), f"Last outbound: {last_outbound.get('deliveryStatus') if last_outbound else 'none'}", "Process a message with AI reply enabled." , severity="warning"),
    ]
    required_failed = [item for item in checklist if item["status"] == "fail" and item["severity"] == "required"]
    warning_count = len([item for item in checklist if item["status"] == "warn"]) + len(failed_logs)
    overall_status = "ready" if not required_failed and not warning_count else ("warning" if not required_failed else "needs_setup")
    return {
        "tenant": serialize_document(tenant),
        "settings": safe_settings,
        "diagnostics": {
            "overallStatus": overall_status,
            "readyForLiveReplies": overall_status in {"ready", "warning"} and bool((integration or {}).get("autoReplyEnabled", True)),
            "webhookUrl": webhook_url,
            "frontendCallbackUrl": callback_url,
            "verifyToken": (integration or {}).get("webhookVerifyToken") or settings.whatsapp_verify_token,
            "checklist": checklist,
            "recentLogs": recent_logs,
            "recentRoutingEvents": recent_events,
            "recentConversations": recent_conversations,
            "failedRecentLogs": len(failed_logs),
            "tips": [
                "Use Mock mode for FYP demo if Meta credentials are not ready.",
                "For live Meta mode, BACKEND_PUBLIC_URL must be an HTTPS ngrok/deployed URL.",
                "Real customer replies are sent only when routing resolves metadata.phone_number_id to this tenant.",
                "If a message is not received, verify webhook URL, verify token, WABA subscription, and phone registration status.",
            ],
        },
    }


async def get_whatsapp_conversation_timeline(tenant_id: str, conversation_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    conversation_oid = parse_object_id(conversation_id, "conversationId")
    conversation = await db.conversations.find_one({"_id": conversation_oid, "tenantId": tenant_oid, "channel": "whatsapp"})
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp conversation not found.")
    messages = await load_conversation_messages(conversation_oid)
    logs_cursor = db.whatsapp_message_logs.find({"conversationId": conversation_oid}).sort("createdAt", 1).limit(100)
    logs = [serialize_document(log) async for log in logs_cursor]
    event_filter = {"tenantId": tenant_oid}
    if conversation.get("createdAt"):
        event_filter["createdAt"] = {"$gte": conversation.get("createdAt")}
    events_cursor = db.whatsapp_routing_events.find(event_filter).sort("createdAt", 1).limit(50)
    events = [serialize_document(event) async for event in events_cursor]
    timeline = []
    for message in messages:
        timeline.append({
            "type": "chat_message",
            "label": "Customer" if message.get("sender") == "user" else "AI Assistant",
            "direction": "inbound" if message.get("sender") == "user" else "outbound",
            "text": message.get("messageText", ""),
            "intent": message.get("intent", ""),
            "confidence": message.get("confidence", 0),
            "createdAt": message.get("createdAt"),
            "raw": message,
        })
    for log in logs:
        timeline.append({
            "type": "provider_log",
            "label": f"Provider {log.get('direction', '')}",
            "direction": log.get("direction", ""),
            "text": log.get("messageText", ""),
            "status": log.get("deliveryStatus") or log.get("providerStatus") or "logged",
            "providerMessageId": log.get("providerMessageId", ""),
            "error": log.get("error", ""),
            "createdAt": log.get("createdAt"),
            "raw": log,
        })
    for event in events:
        timeline.append({
            "type": "routing_event",
            "label": event.get("eventType", "routing_event"),
            "direction": "system",
            "text": event.get("detail", ""),
            "status": event.get("statusText", ""),
            "phoneNumberId": event.get("phoneNumberId", ""),
            "createdAt": event.get("createdAt"),
            "raw": event,
        })
    timeline.sort(key=lambda item: item.get("createdAt") or "")
    return {
        "tenant": serialize_document(tenant),
        "conversation": serialize_document(conversation),
        "messages": messages,
        "providerLogs": logs,
        "routingEvents": events,
        "timeline": timeline,
    }


async def run_whatsapp_live_webhook_test(tenant_id: str, payload: WhatsAppLiveWebhookTestRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid, "isConnected": True})
    if not integration:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connect WhatsApp before running a live webhook test.")
    phone_number_id = (integration.get("phoneNumberId") or "").strip()
    if not phone_number_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone Number ID is missing for this WhatsApp connection.")
    now = datetime.now(timezone.utc)
    provider_message_id = payload.providerMessageId or f"phase-i-live-test-{int(now.timestamp())}"
    display_phone = _digits_only(integration.get("businessWhatsAppNumber") or integration.get("normalizedBusinessWhatsAppNumber") or "")
    from_phone_digits = _digits_only(payload.customerPhone)
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": integration.get("wabaId") or integration.get("whatsappBusinessAccountId") or "phase-i-waba",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": display_phone, "phone_number_id": phone_number_id},
                            "contacts": [{"wa_id": from_phone_digits, "profile": {"name": payload.customerName}}],
                            "messages": [
                                {
                                    "from": from_phone_digits,
                                    "id": provider_message_id,
                                    "timestamp": str(int(now.timestamp())),
                                    "type": "text",
                                    "text": {"body": payload.messageText},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    if not payload.processWithAgent:
        events = _extract_meta_whatsapp_message_events(webhook_payload)
        route = None
        if events:
            routed_integration, routed_tenant = await find_whatsapp_integration_for_inbound(phone_number_id=events[0].get("phoneNumberId"), business_number=events[0].get("displayPhoneNumber"))
            route = {
                "matchedTenantId": str(routed_tenant["_id"]),
                "matchedBusinessName": routed_tenant.get("name", ""),
                "phoneNumberId": routed_integration.get("phoneNumberId", ""),
            }
        await _log_whatsapp_routing_event(
            event_type="phase_i_dry_run",
            phone_number_id=phone_number_id,
            tenant_id=tenant_oid,
            status_text="matched" if route else "skipped",
            detail="Phase I dry-run webhook payload parsed and routed without sending an AI reply.",
            raw_payload=webhook_payload,
        )
        return {
            "mode": "dry_run",
            "webhookPayload": webhook_payload,
            "events": events,
            "routing": route or {},
            "processed": {},
        }
    result = await process_whatsapp_webhook_payload(webhook_payload)
    return {
        "mode": "processed_with_agent",
        "webhookPayload": webhook_payload,
        "processed": result,
    }


def _phase_j_check(code: str, label: str, passed: bool, detail: str, fix: str = "", severity: str = "required") -> dict:
    return {
        "code": code,
        "label": label,
        "status": "pass" if passed else ("warn" if severity == "warning" else "fail"),
        "detail": detail,
        "fix": fix,
        "severity": severity,
    }


def _phase_j_test_result_from_payload(payload) -> str:
    required = [
        bool(payload.realCustomerMessageReceived),
        bool(payload.aiReplyDelivered),
        bool(payload.conversationVisible),
    ]
    advanced = [
        bool(payload.orderFlowTested),
        bool(payload.orderCreated),
        bool(payload.handoffTested),
        bool(payload.ownerNotificationCreated),
    ]
    if getattr(payload, "result", "auto") in {"passed", "warning", "failed"}:
        return payload.result
    if all(required) and (not payload.orderFlowTested or payload.orderCreated):
        return "passed" if any(advanced) else "warning"
    if any(required):
        return "warning"
    return "failed"


async def get_whatsapp_go_live_checklist(tenant_id: str, user: dict) -> dict:
    """Phase J: final live Meta WhatsApp acceptance checklist and owner runbook."""
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    diagnostics = await get_whatsapp_live_diagnostics(tenant_id, user)
    safe_settings = serialize_whatsapp_settings(integration, tenant)
    recent_logs_cursor = db.whatsapp_message_logs.find({"tenantId": tenant_oid}).sort("createdAt", -1).limit(30)
    recent_logs = [serialize_document(log) async for log in recent_logs_cursor]
    recent_conversations_count = await db.conversations.count_documents({"tenantId": tenant_oid, "channel": "whatsapp"})
    whatsapp_orders_count = await db.transactions.count_documents({"tenantId": tenant_oid, "source": "whatsapp"})
    handoff_count = await db.conversations.count_documents({"tenantId": tenant_oid, "channel": "whatsapp", "status": "handoff"})
    inbound_count = len([log for log in recent_logs if log.get("direction") == "inbound"])
    outbound_success_count = len(
        [
            log
            for log in recent_logs
            if log.get("direction") == "outbound" and str(log.get("deliveryStatus") or log.get("providerStatus") or "").lower() not in {"failed", "error"}
        ]
    )
    failed_outbound_count = len(
        [
            log
            for log in recent_logs
            if log.get("direction") == "outbound" and str(log.get("deliveryStatus") or log.get("providerStatus") or "").lower() in {"failed", "error"}
        ]
    )
    latest_run = await db.whatsapp_go_live_runs.find_one({"tenantId": tenant_oid}, sort=[("createdAt", -1)])
    is_meta = bool(integration and integration.get("provider") == "meta_cloud")
    has_token = bool((integration or {}).get("accessToken") or settings.whatsapp_access_token)
    webhook_url = (integration or {}).get("webhookCallbackUrl") or _public_webhook_callback_url()
    public_https = bool(webhook_url and webhook_url.startswith("https://"))
    live_ready = bool(
        integration
        and is_meta
        and ((integration.get("wabaId") or integration.get("whatsappBusinessAccountId")))
        and integration.get("phoneNumberId")
        and has_token
        and public_https
        and integration.get("webhookSubscriptionStatus") == "subscribed"
        and integration.get("phoneRegistrationStatus") == "registered"
        and (integration.get("webhookRoutingStatus") == "active" or integration.get("lastWebhookReceivedAt"))
        and integration.get("agentEnabled", True)
        and integration.get("autoReplyEnabled", True)
    )
    checklist = [
        _phase_j_check("meta_provider", "Meta Cloud provider selected", is_meta, f"Provider: {(integration or {}).get('provider', 'not configured')}", "Connect WhatsApp through Meta Embedded Signup."),
        _phase_j_check("waba_saved", "WABA ID saved", bool((integration or {}).get("wabaId") or (integration or {}).get("whatsappBusinessAccountId")), f"WABA ID: {(integration or {}).get('wabaId') or (integration or {}).get('whatsappBusinessAccountId') or 'missing'}", "Complete Embedded Signup and token exchange."),
        _phase_j_check("phone_id_saved", "Phone Number ID saved", bool((integration or {}).get("phoneNumberId")), f"Phone Number ID: {(integration or {}).get('phoneNumberId') or 'missing'}", "Complete Embedded Signup or save the Meta Phone Number ID."),
        _phase_j_check("business_token", "Business access token saved", has_token, "Token is stored and masked." if has_token else "Business token missing.", "Run Phase D token exchange."),
        _phase_j_check("public_https_webhook", "Public HTTPS webhook URL", public_https, webhook_url or "BACKEND_PUBLIC_URL missing", "Use ngrok/deployed backend URL and set BACKEND_PUBLIC_URL."),
        _phase_j_check("webhook_subscribed", "WABA webhooks subscribed", bool((integration or {}).get("webhookSubscriptionStatus") == "subscribed"), f"Status: {(integration or {}).get('webhookSubscriptionStatus') or 'pending'}", "Run Phase E webhook subscription."),
        _phase_j_check("phone_registered", "Phone registered for Cloud API", bool((integration or {}).get("phoneRegistrationStatus") == "registered"), f"Status: {(integration or {}).get('phoneRegistrationStatus') or 'pending'}", "Run Phase F phone registration."),
        _phase_j_check("routing_active", "Phone Number ID routing active", bool((integration or {}).get("webhookRoutingStatus") == "active" or (integration or {}).get("lastWebhookReceivedAt")), f"Status: {(integration or {}).get('webhookRoutingStatus') or 'not tested'}", "Run Phase G routing test or send a real WhatsApp message."),
        _phase_j_check("agent_enabled", "AI agent and auto reply enabled", bool((integration or {}).get("agentEnabled", True) and (integration or {}).get("autoReplyEnabled", True)), "Agent is enabled." if (integration or {}).get("agentEnabled", True) and (integration or {}).get("autoReplyEnabled", True) else "Agent or auto reply is off.", "Enable Agent and Auto Reply in WhatsApp settings."),
        _phase_j_check("real_inbound_seen", "Live/mock inbound message seen", inbound_count > 0, f"Recent inbound logs: {inbound_count}", "Send a customer WhatsApp message or use the mock simulator.", severity="warning"),
        _phase_j_check("outbound_reply_seen", "AI outbound reply logged", outbound_success_count > 0, f"Recent successful outbound logs: {outbound_success_count}", "Process a WhatsApp message with auto reply enabled.", severity="warning"),
        _phase_j_check("orders_verified", "WhatsApp order flow tested", whatsapp_orders_count > 0, f"WhatsApp transactions: {whatsapp_orders_count}", "Run the order test: item request → delivery/pickup → address → confirm.", severity="warning"),
        _phase_j_check("handoff_verified", "Human handoff tested", handoff_count > 0, f"Handoff conversations: {handoff_count}", "Send a handoff keyword like 'human se baat karni hai'.", severity="warning"),
        _phase_j_check("recent_failures", "No recent outbound failures", failed_outbound_count == 0, f"Recent failed outbound logs: {failed_outbound_count}", "Open diagnostics and fix provider/token/recipient errors.", severity="warning"),
        _phase_j_check("manual_signoff", "Manual go-live test run recorded", bool(latest_run and latest_run.get("result") in {"passed", "warning"}), f"Latest run: {(latest_run or {}).get('result', 'none')}", "Record the Phase J test run after real/mocked customer testing.", severity="warning"),
    ]
    required_failed = [item for item in checklist if item["severity"] == "required" and item["status"] == "fail"]
    warnings = [item for item in checklist if item["status"] == "warn"]
    overall_status = "ready_for_live" if live_ready and not required_failed and not failed_outbound_count else ("ready_for_demo" if not required_failed else "needs_setup")
    return {
        "tenant": serialize_document(tenant),
        "settings": safe_settings,
        "phaseJ": {
            "overallStatus": overall_status,
            "readyForLive": overall_status == "ready_for_live",
            "readyForDemo": overall_status in {"ready_for_live", "ready_for_demo"},
            "checklist": checklist,
            "requiredFailures": len(required_failed),
            "warningCount": len(warnings),
            "recentCounts": {
                "whatsappConversations": recent_conversations_count,
                "recentInboundLogs": inbound_count,
                "recentOutboundReplies": outbound_success_count,
                "recentOutboundFailures": failed_outbound_count,
                "whatsappTransactions": whatsapp_orders_count,
                "handoffConversations": handoff_count,
            },
            "latestRun": serialize_document(latest_run) if latest_run else None,
            "diagnosticsSummary": diagnostics.get("diagnostics", {}),
            "runbook": [
                "Open the business public/customer WhatsApp link or message the connected Meta test number directly.",
                "Send: 'Zinger burger available hai?' and confirm the agent replies from catalog/RAG.",
                "Send: '2 zinger burgers order kar do', then answer delivery/pickup, address/city, and confirm.",
                "Confirm the order appears in Transactions and stock is reserved.",
                "Send a handoff phrase such as 'human se baat karni hai' and confirm owner notification/handoff status.",
                "Open the WhatsApp conversation timeline and verify inbound message, AI reply, provider logs, and routing events.",
                "Record the Phase J test run below before final demo/submission.",
            ],
        },
    }


async def record_whatsapp_go_live_test_run(tenant_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_whatsapp_owner(tenant_id, user)
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid})
    now = datetime.now(timezone.utc)
    result = _phase_j_test_result_from_payload(payload)
    run = {
        "tenantId": tenant_oid,
        "recordedByUserId": user.get("_id"),
        "provider": (integration or {}).get("provider", "not_configured"),
        "phoneNumberId": (integration or {}).get("phoneNumberId", ""),
        "wabaId": (integration or {}).get("wabaId") or (integration or {}).get("whatsappBusinessAccountId", ""),
        "customerPhone": normalize_phone(payload.customerPhone),
        "customerName": payload.customerName,
        "testMessage": payload.testMessage,
        "realCustomerMessageReceived": bool(payload.realCustomerMessageReceived),
        "aiReplyDelivered": bool(payload.aiReplyDelivered),
        "conversationVisible": bool(payload.conversationVisible),
        "orderFlowTested": bool(payload.orderFlowTested),
        "orderCreated": bool(payload.orderCreated),
        "handoffTested": bool(payload.handoffTested),
        "ownerNotificationCreated": bool(payload.ownerNotificationCreated),
        "notes": payload.notes.strip(),
        "result": result,
        "createdAt": now,
        "updatedAt": now,
    }
    run["_id"] = (await db.whatsapp_go_live_runs.insert_one(run)).inserted_id
    checklist = await get_whatsapp_go_live_checklist(tenant_id, user)
    return {
        "tenant": serialize_document(tenant),
        "settings": serialize_whatsapp_settings(integration, tenant),
        "testRun": serialize_document(run),
        "phaseJ": checklist["phaseJ"],
    }
