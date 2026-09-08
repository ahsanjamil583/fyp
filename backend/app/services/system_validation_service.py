from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ai.rag.chroma_client import chroma_client
from app.core.config import settings
from app.db.mongodb import get_database, get_mongo_status


SAFE_PROVIDER_VALUES = {"mock", "baileys", "http", "local", "imagekit", "disabled", ""}


def _mask_secret(value: str) -> str:
    """Report only whether a secret is configured.

    Echoing a prefix and suffix leaks enough to identify the key and narrow a search
    for it, and the readiness report is reachable by anyone who can call the API.
    """
    return "set" if value else "not_set"


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


def build_whatsapp_readiness() -> dict[str, Any]:
    # The Meta webhook route was retired with the move to the Baileys bridge; the bridge
    # posts inbound messages here instead.
    webhook_callback = (
        f"{settings.backend_public_url}{settings.api_v1_prefix}/whatsapp/bridge/inbound"
        if settings.backend_public_url
        else ""
    )
    checks = [
        {
            "code": "whatsapp_provider",
            "label": "WhatsApp provider",
            "status": "pass" if settings.whatsapp_provider in SAFE_PROVIDER_VALUES else "missing",
            "message": f"WhatsApp provider: {settings.whatsapp_provider or 'not configured'}.",
        },
        {
            "code": "webhook_verify_token",
            "label": "Webhook verify token",
            "status": "pass" if settings.whatsapp_verify_token else "missing",
            "message": "Webhook verify token is configured." if settings.whatsapp_verify_token else "Set WHATSAPP_VERIFY_TOKEN.",
        },
    ]
    if settings.backend_public_url:
        checks.append(
            {
                "code": "backend_public_url",
                "label": "Backend public URL",
                "status": "pass" if _is_public_https_url(settings.backend_public_url) else "missing",
                "message": webhook_callback or "Set BACKEND_PUBLIC_URL to a public HTTPS backend URL.",
            }
        )
    missing = [check["code"] for check in checks if check["status"] != "pass"]
    return {
        "ready": not missing,
        "status": "ready" if not missing else "needs_setup",
        "missing": missing,
        "checks": checks,
        "webhookCallbackUrl": webhook_callback,
        "webhookVerifyToken": settings.whatsapp_verify_token,
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


async def _disconnected_whatsapp_integrations(mongo: dict[str, Any]) -> list[str]:
    """Names of businesses whose WhatsApp stopped working.

    A migration or a WhatsApp-side logout leaves the integration in place but unable to
    send or receive, which is otherwise invisible until a customer is ignored.
    """
    if not mongo.get("connected"):
        return []
    try:
        db = get_database()
        names: list[str] = []
        query = {"$or": [{"status": "needs_reconnect"}, {"bridgeStatus": {"$in": ["logged_out", "connection_failed"]}}]}
        async for integration in db.whatsapp_integrations.find(query, {"tenantId": 1}):
            tenant = await db.tenants.find_one({"_id": integration.get("tenantId")}, {"name": 1})
            names.append((tenant or {}).get("name", str(integration.get("tenantId"))))
        return names
    except Exception:
        # A readiness probe reports problems; it must not become one.
        return []


async def build_readiness_report() -> dict[str, Any]:
    mongo = await get_mongo_status()
    chroma = chroma_client.status()
    upload_dir = _directory_status(settings.local_upload_dir)
    temp_dir = _directory_status(settings.temp_upload_dir)
    log_dir = _directory_status(settings.log_dir)
    demo_seed = await _demo_seed_status(mongo)
    whatsapp_readiness = build_whatsapp_readiness()
    disconnected = await _disconnected_whatsapp_integrations(mongo)

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
            "status": "fail" if settings.jwt_secret_is_public and settings.app_env == "production" else ("pass" if not settings.jwt_secret_is_public else "warn"),
            "message": (
                "JWT secret is private and long enough."
                if not settings.jwt_secret_is_public
                else "JWT_SECRET_KEY is a known placeholder or too short. Rotate it before deploying."
            ),
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
            "code": "whatsapp_readiness",
            "label": "WhatsApp readiness",
            "status": "pass" if whatsapp_readiness["ready"] else "warn",
            "message": "WhatsApp base setup is ready." if whatsapp_readiness["ready"] else f"Missing WhatsApp setup: {', '.join(whatsapp_readiness['missing'])}.",
        },
        {
            "code": "whatsapp_connections",
            "label": "WhatsApp connections",
            "status": "pass" if not disconnected else "warn",
            "message": (
                "All WhatsApp integrations are connected."
                if not disconnected
                else f"{len(disconnected)} WhatsApp integration(s) need re-pairing: {', '.join(disconnected)}."
            ),
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
            "whatsapp": whatsapp_readiness,
        },
        "integrations": {
            "whatsapp": {
                "provider": settings.whatsapp_provider,
                "backendPublicUrl": settings.backend_public_url or "not_set",
                "webhookCallbackUrl": whatsapp_readiness["webhookCallbackUrl"],
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
    if settings.app_env == "production":
        return {
            "available": False,
            "note": "Demo account credentials are not published in production.",
        }
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
