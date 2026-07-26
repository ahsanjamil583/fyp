from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ai.rag.chroma_client import chroma_client
from app.core.config import settings
from app.db.mongodb import get_database, get_mongo_status


SAFE_PROVIDER_VALUES = {"mock", "meta", "http", "local", "imagekit", "disabled", ""}


def _mask_secret(value: str) -> str:
    if not value:
        return "not_set"
    if len(value) <= 8:
        return "set"
    return f"set:{value[:3]}...{value[-3:]}"


def _directory_status(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".bizxus_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        writable = True
    except Exception as exc:
        writable = False
        return {"path": str(path), "exists": path.exists(), "writable": writable, "error": str(exc)}
    return {"path": str(path), "exists": path.exists(), "writable": writable}


def _is_public_https_url(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized.startswith("https://") and "localhost" not in normalized and "127.0.0.1" not in normalized


def build_meta_embedded_signup_readiness() -> dict[str, Any]:
    frontend_callback = f"{settings.frontend_base_url}{settings.meta_business_login_redirect_path}"
    webhook_callback = (
        f"{settings.backend_public_url}{settings.api_v1_prefix}/webhooks/whatsapp"
        if settings.backend_public_url
        else ""
    )
    checks = [
        {
            "code": "meta_app_id",
            "label": "Meta App ID",
            "status": "pass" if settings.meta_app_id else "missing",
            "message": "Meta App ID is configured." if settings.meta_app_id else "Add META_APP_ID from Meta Developer Dashboard.",
        },
        {
            "code": "meta_app_secret",
            "label": "Meta App Secret",
            "status": "pass" if settings.meta_app_secret else "missing",
            "message": "Meta App Secret is configured." if settings.meta_app_secret else "Add META_APP_SECRET. Never expose it in frontend.",
        },
        {
            "code": "embedded_signup_config",
            "label": "Embedded Signup Configuration ID",
            "status": "pass" if settings.meta_embedded_signup_config_id else "missing",
            "message": "Embedded Signup Configuration ID is configured." if settings.meta_embedded_signup_config_id else "Add META_EMBEDDED_SIGNUP_CONFIG_ID.",
        },
        {
            "code": "frontend_callback",
            "label": "Frontend callback URL",
            "status": "pass" if settings.frontend_base_url else "missing",
            "message": frontend_callback if settings.frontend_base_url else "Set FRONTEND_BASE_URL.",
        },
        {
            "code": "backend_public_url",
            "label": "Backend public HTTPS URL",
            "status": "pass" if _is_public_https_url(settings.backend_public_url) else "missing",
            "message": webhook_callback or "Set BACKEND_PUBLIC_URL to an HTTPS ngrok/Railway URL. Meta webhooks cannot use localhost.",
        },
        {
            "code": "webhook_verify_token",
            "label": "Webhook verify token",
            "status": "pass" if settings.whatsapp_verify_token else "missing",
            "message": "Webhook verify token is configured." if settings.whatsapp_verify_token else "Set WHATSAPP_VERIFY_TOKEN.",
        },
    ]
    missing = [check["code"] for check in checks if check["status"] != "pass"]
    return {
        "ready": not missing,
        "status": "ready" if not missing else "needs_setup",
        "missing": missing,
        "checks": checks,
        "metaAppId": settings.meta_app_id,
        "embeddedSignupConfigId": settings.meta_embedded_signup_config_id,
        "graphApiVersion": settings.meta_graph_api_version,
        "frontendCallbackUrl": frontend_callback,
        "webhookCallbackUrl": webhook_callback,
        "webhookVerifyToken": settings.whatsapp_verify_token,
        "requiredScopes": ["whatsapp_business_management", "whatsapp_business_messaging", "business_management"],
    }


async def _demo_seed_status(mongo: dict[str, Any]) -> dict[str, Any]:
    if not mongo.get("connected"):
        return {
            "available": False,
            "message": "MongoDB is not connected, so demo seed data could not be inspected.",
            "counts": {},
        }
    try:
        db = get_database()
        tenant = await db.tenants.find_one({"slug": "demo-bazaar"})
        if not tenant:
            return {
                "available": False,
                "message": "Demo tenant is missing. Run `python scripts/seed_demo_data.py` from backend.",
                "counts": {"tenant": 0},
            }
        tenant_id = tenant["_id"]
        counts = {
            "tenant": 1,
            "activeItems": await db.items.count_documents({"tenantId": tenant_id, "status": "active"}),
            "knowledgeDocuments": await db.knowledge_documents.count_documents({"tenantId": tenant_id, "isActive": True}),
            "paymentSettings": await db.payment_settings.count_documents({"tenantId": tenant_id}),
            "reportSettings": await db.report_delivery_settings.count_documents({"tenantId": tenant_id}),
            "reportLogs": await db.report_delivery_logs.count_documents({"tenantId": tenant_id}),
            "whatsappIntegrations": await db.whatsapp_integrations.count_documents({"tenantId": tenant_id, "isConnected": True}),
        }
        required = ["activeItems", "knowledgeDocuments", "paymentSettings", "reportSettings", "whatsappIntegrations"]
        missing = [key for key in required if counts.get(key, 0) < 1]
        return {
            "available": not missing,
            "message": "Demo seed data is ready." if not missing else f"Demo seed is incomplete: missing {', '.join(missing)}.",
            "counts": counts,
        }
    except Exception as exc:
        return {
            "available": False,
            "message": f"Demo seed inspection failed: {exc}",
            "counts": {},
        }


async def build_readiness_report() -> dict[str, Any]:
    mongo = await get_mongo_status()
    chroma = chroma_client.status()
    upload_dir = _directory_status(settings.local_upload_dir)
    temp_dir = _directory_status(settings.temp_upload_dir)
    log_dir = _directory_status(settings.log_dir)
    demo_seed = await _demo_seed_status(mongo)
    meta_embedded_signup = build_meta_embedded_signup_readiness()

    checks = [
        {
            "code": "mongodb",
            "label": "MongoDB connection",
            "status": "pass" if mongo.get("connected") else "warn",
            "message": "MongoDB is reachable." if mongo.get("connected") else "MongoDB is not reachable. Start MongoDB before using database-backed features.",
        },
        {
            "code": "chroma",
            "label": "Chroma / RAG vector store",
            "status": "pass" if chroma.get("connected") or chroma.get("mode") == "persistent" else "warn",
            "message": f"Chroma status: {chroma.get('mode', 'unknown')}.",
        },
        {
            "code": "jwt_secret",
            "label": "JWT secret",
            "status": "fail" if settings.app_env == "production" and settings.jwt_secret_key in {"", "change-this-secret", "changeme", "secret"} else "pass",
            "message": "JWT secret is configured." if settings.jwt_secret_key not in {"", "change-this-secret", "changeme", "secret"} else "Use a strong JWT_SECRET_KEY before production.",
        },
        {
            "code": "debug_mode",
            "label": "Debug mode",
            "status": "fail" if settings.app_env == "production" and settings.debug else "pass",
            "message": "Debug mode is disabled for production." if not settings.debug else "DEBUG=true is acceptable for local development only.",
        },
        {
            "code": "uploads",
            "label": "Upload directories",
            "status": "pass" if upload_dir.get("writable") and temp_dir.get("writable") else "fail",
            "message": "Upload directories are writable." if upload_dir.get("writable") and temp_dir.get("writable") else "Upload directory is not writable.",
        },
        {
            "code": "logging",
            "label": "Log directory",
            "status": "pass" if log_dir.get("writable") else "warn",
            "message": "Log directory is writable." if log_dir.get("writable") else "Log directory could not be written.",
        },
        {
            "code": "whatsapp_provider",
            "label": "WhatsApp provider",
            "status": "pass" if settings.whatsapp_provider in SAFE_PROVIDER_VALUES else "warn",
            "message": f"WhatsApp provider: {settings.whatsapp_provider or 'not configured'}.",
        },
        {
            "code": "meta_embedded_signup",
            "label": "Meta Embedded Signup readiness",
            "status": "pass" if meta_embedded_signup["ready"] else "warn",
            "message": "Meta Embedded Signup env is ready." if meta_embedded_signup["ready"] else f"Missing Meta setup: {', '.join(meta_embedded_signup['missing'])}.",
        },
        {
            "code": "sms_provider",
            "label": "SMS provider",
            "status": "pass" if settings.sms_provider in SAFE_PROVIDER_VALUES else "warn",
            "message": f"SMS provider: {settings.sms_provider or 'not configured'}.",
        },

        {
            "code": "otp_settings",
            "label": "Phone OTP auth",
            "status": "pass" if settings.otp_code_length >= 4 and settings.otp_expire_minutes >= 1 else "fail",
            "message": f"OTP enabled with {settings.otp_code_length}-digit codes and {settings.otp_expire_minutes} minute expiry.",
        },
        {
            "code": "rate_limit",
            "label": "Rate limiting",
            "status": "pass" if settings.rate_limit_enabled else "warn",
            "message": "Basic API rate limiting is enabled." if settings.rate_limit_enabled else "Rate limiting is disabled. Enable it or use gateway rate limiting before public deployment.",
        },
        {
            "code": "demo_seed",
            "label": "Final demo seed data",
            "status": "pass" if demo_seed.get("available") else "warn",
            "message": demo_seed.get("message", "Demo seed status unavailable."),
        },
    ]

    totals = {
        "pass": sum(1 for check in checks if check["status"] == "pass"),
        "warn": sum(1 for check in checks if check["status"] == "warn"),
        "fail": sum(1 for check in checks if check["status"] == "fail"),
    }
    if totals["fail"]:
        overall = "not_ready"
    elif totals["warn"]:
        overall = "ready_with_warnings"
    else:
        overall = "ready"

    return {
        "overallStatus": overall,
        "totals": totals,
        "checks": checks,
        "runtime": {
            "appName": settings.app_name,
            "appVersion": settings.app_version,
            "buildLabel": settings.build_label,
            "environment": settings.app_env,
            "debug": settings.debug,
            "apiPrefix": settings.api_v1_prefix,
        },
        "services": {
            "mongodb": mongo,
            "chroma": chroma,
            "uploads": upload_dir,
            "tempUploads": temp_dir,
            "logs": log_dir,
            "demoSeed": demo_seed,
            "metaEmbeddedSignup": meta_embedded_signup,
        },
        "integrations": {
            "whatsapp": {
                "provider": settings.whatsapp_provider,
                "phoneNumberId": _mask_secret(settings.whatsapp_phone_number_id),
                "accessToken": _mask_secret(settings.whatsapp_access_token),
                "metaAppId": _mask_secret(settings.meta_app_id),
                "embeddedSignupConfigId": _mask_secret(settings.meta_embedded_signup_config_id),
                "backendPublicUrl": settings.backend_public_url or "not_set",
                "frontendCallbackUrl": meta_embedded_signup["frontendCallbackUrl"],
                "webhookCallbackUrl": meta_embedded_signup["webhookCallbackUrl"],
            },
            "sms": {
                "provider": settings.sms_provider,
                "apiKey": _mask_secret(settings.sms_api_key),
                "httpUrl": "set" if settings.sms_http_url else "not_set",
                "senderId": settings.sms_sender_id,
            },
            "otp": {
                "codeLength": settings.otp_code_length,
                "expireMinutes": settings.otp_expire_minutes,
                "maxAttempts": settings.otp_max_attempts,
                "returnCodeInResponse": settings.otp_return_code_in_response and settings.app_env != "production",
            },
            "ai": {
                "openaiKey": _mask_secret(settings.openai_api_key),
                "groqKey": _mask_secret(settings.groq_api_key),
                "model": settings.groq_model or settings.openai_model,
                "embeddingModel": settings.openai_embedding_model,
            },
        },
    }


def build_demo_accounts() -> dict[str, Any]:
    return {
        "businessOwner": {
            "email": "owner@bizxus.demo",
            "phone": "03000000001",
            "password": "Demo@12345",
            "demoOtp": settings.otp_demo_code,
            "loginPath": "/login",
        },
        "customer": {
            "email": "customer@bizxus.demo",
            "phone": "03000000002",
            "password": "Demo@12345",
            "demoOtp": settings.otp_demo_code,
            "loginPath": "/customer/login",
        },
        "admin": {
            "email": "admin@bizxus.demo",
            "password": "Admin@12345",
            "loginPath": "/login",
            "note": "Created only when the demo seed script is run.",
        },
        "businessSlug": "demo-bazaar",
    }
