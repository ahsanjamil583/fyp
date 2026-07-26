from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.module_service import PLAN_ORDER, enable_tenant_module, list_tenant_modules
from app.services.module_service import get_package_access_status, get_plan_definition
from app.services.tenant_service import publish_tenant
from app.services.whatsapp_service import normalize_phone

LAUNCH_PROFILES: dict[str, dict[str, Any]] = {
    "basic_website": {
        "name": "Basic",
        "priceLabel": "Free",
        "isPaid": False,
        "description": "Free website, basic catalog/items, public website, simple dashboard, and manual orders/inquiries.",
        "targetPlan": "starter",
        "features": ["Business profile", "Basic catalog/items", "Public website", "Basic dashboard", "Manual orders/inquiries"],
        "modules": ["items", "website_builder", "analytics", "notifications"],
    },
    "ai_ordering": {
        "name": "AI Ordering",
        "priceLabel": "Paid",
        "isPaid": True,
        "description": "Paid package with customer portal, AI chat, RAG, smart ordering, payments, and stock-aware ordering.",
        "targetPlan": "growth",
        "features": ["Everything in Basic", "Customer portal", "AI chat", "RAG knowledge base", "Smart order drafts", "Payments", "Stock-aware ordering"],
        "modules": ["items", "customers", "website_builder", "customer_portal", "ai_chat", "analytics", "payments", "notifications"],
    },
    "full_agent_demo": {
        "name": "Full Agent",
        "priceLabel": "Paid",
        "isPaid": True,
        "description": "Paid package with WhatsApp agent, owner AI assistant, daily reports, advanced agent tools, and full automation demo features.",
        "targetPlan": "scale",
        "features": ["Everything in AI Ordering", "WhatsApp agent", "Owner AI assistant", "Daily WhatsApp/SMS reports", "Agent tools", "Advanced reports", "Full automation demo"],
        "modules": [
            "items",
            "customers",
            "website_builder",
            "customer_portal",
            "ai_chat",
            "whatsapp_agent",
            "owner_agent",
            "analytics",
            "payments",
            "reports",
            "notifications",
        ],
    },
}


def normalize_launch_profile(profile_code: str | None) -> str:
    code = str(profile_code or "ai_ordering").strip().lower()
    return code if code in LAUNCH_PROFILES else "ai_ordering"


def _is_platform_admin(user: dict) -> bool:
    return user.get("globalRole") == "platform_admin"


def _profile_access_status(tenant: dict, profile: dict) -> str:
    if not profile.get("isPaid"):
        return "approved"
    return get_package_access_status(tenant, profile.get("targetPlan"))


def plan_rank(plan_code: str | None) -> int:
    normalized = str(plan_code or "starter").strip().lower()
    return PLAN_ORDER.index(normalized) if normalized in PLAN_ORDER else 0


def highest_required_plan(current_plan: str | None, target_plan: str | None) -> str:
    current = str(current_plan or "starter").strip().lower()
    target = str(target_plan or "starter").strip().lower()
    current = current if current in PLAN_ORDER else "starter"
    target = target if target in PLAN_ORDER else "starter"
    return current if plan_rank(current) >= plan_rank(target) else target


def _safe_number(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _contact_phone(tenant: dict) -> str:
    contact = tenant.get("contact") or {}
    return normalize_phone(contact.get("whatsapp") or contact.get("phone") or "")


def _launch_website_settings(tenant: dict, category: dict) -> dict:
    existing = tenant.get("websiteSettings") or {}
    if existing.get("templateCode"):
        return existing
    hints = category.get("websiteHints") or {}
    template_code = hints.get("recommendedTemplate") or "catalog"
    primary_color = hints.get("recommendedPrimaryColor") or "#2563EB"
    visual_preset = "studio" if template_code == "service" else "market" if template_code == "catalog" else "harbor"
    business_name = tenant.get("name") or "Your Business"
    return {
        "templateCode": template_code,
        "visualPreset": visual_preset,
        "primaryColor": primary_color,
        "hero": {
            "headline": f"{business_name} is ready for online orders",
            "subheadline": "Browse offers, ask the AI assistant, and place requests from one simple public website.",
            "ctaLabel": "Chat with AI",
            "secondaryCtaLabel": "Browse catalog",
        },
        "sections": [
            {"type": "hero", "label": "Hero", "visible": True, "order": 1, "content": {}},
            {"type": "catalog", "label": "Catalog", "visible": True, "order": 2, "content": {}},
            {"type": "faq", "label": "FAQ", "visible": True, "order": 3, "content": {}},
            {"type": "contact", "label": "Contact", "visible": True, "order": 4, "content": {}},
        ],
        "faq": [],
        "testimonials": [],
        "seo": {"title": business_name},
    }


def build_launch_payment_defaults(tenant_oid: ObjectId, user_id: ObjectId | None = None) -> dict[str, Any]:
    return {
        "tenantId": tenant_oid,
        "codEnabled": True,
        "manualEnabled": True,
        "bankTransferEnabled": True,
        "jazzCashEnabled": False,
        "easyPaisaEnabled": False,
        "paymentsDemoMode": True,
        "requireOwnerApproval": True,
        "bankName": "",
        "jazzCashNumber": "",
        "jazzCashAccountTitle": "",
        "easyPaisaNumber": "",
        "easyPaisaAccountTitle": "",
        "bankAccountTitle": "",
        "bankAccountNumber": "",
        "bankIban": "",
        "defaultMethod": "cod",
        "customerInstructions": "COD and manual payment verification are available for launch. Mock wallet options can be enabled later.",
        "createdBy": user_id,
    }


def build_launch_report_defaults(tenant_oid: ObjectId, tenant: dict) -> dict[str, Any]:
    phone = _contact_phone(tenant)
    return {
        "tenantId": tenant_oid,
        "enabled": True,
        "whatsappEnabled": bool(phone),
        "smsEnabled": False,
        "deliveryTime": "21:00",
        "timezone": ((tenant.get("settings") or {}).get("timezone")) or "Asia/Karachi",
        "whatsappRecipient": phone,
        "smsRecipient": phone,
        "languageMode": ((tenant.get("settings") or {}).get("languageMode")) or "mixed",
        "includeLowStock": True,
        "includeTopItems": True,
        "includeRecentOrders": True,
        "lastDeliveryStatus": "not_delivered",
    }


def build_launch_whatsapp_defaults(tenant_oid: ObjectId, tenant: dict) -> dict[str, Any]:
    phone = normalize_phone(((tenant.get("contact") or {}).get("whatsapp") or "").strip())
    return {
        "tenantId": tenant_oid,
        "provider": "mock",
        "businessWhatsAppNumber": phone,
        "normalizedBusinessWhatsAppNumber": phone,
        "displayName": tenant.get("name", ""),
        "phoneNumberId": f"launch-{tenant_oid}-mock",
        "apiVersion": "v21.0",
        "webhookVerifyToken": f"launch-{tenant_oid}-verify",
        "accessToken": "",
        "isConnected": bool(phone),
        "autoReplyEnabled": True,
        "handoffEnabled": True,
        "handoffKeywords": ["human", "agent", "admin", "owner"],
        "welcomeMessage": "Assalam o Alaikum! Main business ka BizXus AI assistant hoon. Aap products, prices, delivery, ya order ke bare mein pooch sakte hain.",
        "status": "connected_mock" if phone else "needs_phone",
    }


def _check(code: str, title: str, completed: bool, description: str, actionLabel: str = "", route: str = "", required: bool = True, meta: dict | None = None) -> dict:
    return {
        "code": code,
        "title": title,
        "description": description,
        "completed": bool(completed),
        "required": bool(required),
        "status": "complete" if completed else ("missing" if required else "optional"),
        "actionLabel": actionLabel,
        "route": route,
        "meta": meta or {},
    }


async def _load_launch_context(tenant_id: str, user: dict) -> tuple[ObjectId, dict, dict, dict]:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    category = None
    if tenant.get("businessCategoryId"):
        category = await db.business_categories.find_one({"_id": tenant.get("businessCategoryId")})
    module_state = await list_tenant_modules(tenant_id, user)
    enabled = set((module_state.get("tenant") or {}).get("enabledModuleCodes") or tenant.get("enabledModuleCodes") or [])
    counts = {
        "activeItems": await db.items.count_documents({"tenantId": tenant_oid, "status": "active"}),
        "sellableItems": await db.items.count_documents({"tenantId": tenant_oid, "status": "active", "$or": [{"isSellable": True}, {"isBookable": True}]}),
        "knowledgeDocuments": await db.knowledge_documents.count_documents({"tenantId": tenant_oid, "isActive": True}),
        "customers": await db.customers.count_documents({"tenantId": tenant_oid}),
        "transactions": await db.transactions.count_documents({"tenantId": tenant_oid}),
        "whatsappConnected": await db.whatsapp_integrations.count_documents({"tenantId": tenant_oid, "isConnected": True}),
        "paymentSettings": await db.payment_settings.count_documents({"tenantId": tenant_oid}),
        "reportSettings": await db.report_delivery_settings.count_documents({"tenantId": tenant_oid, "enabled": True}),
    }
    payment_settings = await db.payment_settings.find_one({"tenantId": tenant_oid}) or {}
    counts["localPaymentsEnabled"] = any(
        bool(payment_settings.get(key)) for key in ["codEnabled", "manualEnabled", "jazzCashEnabled", "easyPaisaEnabled"]
    )
    return tenant_oid, tenant, category or {}, {"modules": module_state, "enabled": enabled, "counts": counts}


def _profile_complete(tenant: dict) -> bool:
    contact = tenant.get("contact") or {}
    address = tenant.get("address") or {}
    return all(
        [
            str(tenant.get("name") or "").strip(),
            tenant.get("businessCategoryId"),
            str(tenant.get("description") or "").strip(),
            str(contact.get("phone") or contact.get("email") or "").strip(),
            str(address.get("city") or "").strip(),
            str(address.get("province") or "").strip(),
        ]
    )


def build_launch_checks(tenant: dict, category: dict, enabled_modules: set[str], counts: dict) -> list[dict]:
    contact = tenant.get("contact") or {}
    profile_meta = {
        "hasName": bool(str(tenant.get("name") or "").strip()),
        "hasCategory": bool(tenant.get("businessCategoryId")),
        "hasDescription": bool(str(tenant.get("description") or "").strip()),
        "hasContact": bool(str(contact.get("phone") or contact.get("email") or "").strip()),
    }
    profile_code = normalize_launch_profile((((tenant.get("settings") or {}).get("onboarding") or {}).get("phase28") or {}).get("profileCode"))
    profile = LAUNCH_PROFILES[profile_code]
    suggested_modules = profile.get("modules") or category.get("suggestedModules") or ["items", "website_builder", "analytics", "notifications"]
    missing_suggested = [code for code in suggested_modules if code not in enabled_modules]
    website_ready = "website_builder" in enabled_modules and bool((tenant.get("websiteSettings") or {}).get("templateCode"))
    requires_ai = profile_code in {"ai_ordering", "full_agent_demo"}
    requires_full_agent = profile_code == "full_agent_demo"
    ai_ready = "ai_chat" in enabled_modules and counts.get("knowledgeDocuments", 0) > 0
    ordering_ready = (
        "customer_portal" in enabled_modules
        and "payments" in enabled_modules
        and counts.get("sellableItems", 0) > 0
        and counts.get("paymentSettings", 0) > 0
        and counts.get("localPaymentsEnabled")
    )

    return [
        _check(
            "business_profile",
            "Business profile is complete",
            _profile_complete(tenant),
            "Add business name, category, phone/email, location, and description so customers and AI understand this business.",
            "Complete profile",
            "/dashboard/business",
            True,
            profile_meta,
        ),
        _check(
            "launch_modules",
            "Recommended launch modules are enabled",
            len(missing_suggested) == 0,
            "Enable the modules suggested for this business category, or use one-click launch profiles.",
            "Enable modules",
            "/dashboard/modules",
            True,
            {"suggestedModules": suggested_modules, "missingModules": missing_suggested},
        ),
        _check(
            "catalog_ready",
            "Catalog or service list is ready",
            counts.get("sellableItems", 0) > 0,
            "Add at least one active sellable/bookable item so customers and the AI can answer product or service requests.",
            "Add/import items",
            "/dashboard/items/import",
            True,
            {"activeItems": counts.get("activeItems", 0), "sellableItems": counts.get("sellableItems", 0)},
        ),
        _check(
            "website_ready",
            "Website builder is ready",
            website_ready,
            "Website settings and template are generated. This must be ready before publishing the public business site.",
            "Open website builder",
            "/dashboard/public-website",
            True,
            {"websiteStatus": tenant.get("websiteStatus", "not_generated"), "templateCode": (tenant.get("websiteSettings") or {}).get("templateCode", "")},
        ),
        _check(
            "ai_rag_ready",
            "AI + RAG has business knowledge",
            ai_ready,
            "Enable AI Chat and add at least one knowledge document so customer, public, and WhatsApp agents reply with grounded business information.",
            "Add knowledge",
            "/dashboard/knowledge-base",
            requires_ai,
            {"knowledgeDocuments": counts.get("knowledgeDocuments", 0), "aiEnabled": "ai_chat" in enabled_modules},
        ),
        _check(
            "ordering_ready",
            "Customer ordering flow is ready",
            ordering_ready,
            "Customer portal, sellable items, and payments should be ready before customers place orders through chat or checkout.",
            "Review payments",
            "/dashboard/payments",
            requires_ai,
            {
                "customerPortalEnabled": "customer_portal" in enabled_modules,
                "paymentsEnabled": "payments" in enabled_modules,
                "paymentSettings": counts.get("paymentSettings", 0),
                "localPaymentsEnabled": counts.get("localPaymentsEnabled", False),
            },
        ),
        _check(
            "whatsapp_ready",
            "WhatsApp agent is connected",
            "whatsapp_agent" in enabled_modules and counts.get("whatsappConnected", 0) > 0,
            "Connect the owner's WhatsApp number so BizXus AI can handle the customer queries that were previously handled manually.",
            "Connect WhatsApp",
            "/dashboard/whatsapp-agent",
            requires_full_agent,
            {"whatsappEnabled": "whatsapp_agent" in enabled_modules, "connectedIntegrations": counts.get("whatsappConnected", 0)},
        ),
        _check(
            "daily_reports_ready",
            "Daily owner reports are scheduled",
            "reports" in enabled_modules and counts.get("reportSettings", 0) > 0,
            "Configure daily WhatsApp/SMS report delivery for owner summaries, low stock, top items, and order updates.",
            "Configure reports",
            "/dashboard/reports",
            requires_full_agent,
            {"reportsEnabled": "reports" in enabled_modules, "reportSettings": counts.get("reportSettings", 0)},
        ),
    ]


def summarize_launch_status(checks: list[dict], tenant: dict, profile_code: str = "ai_ordering") -> dict:
    required = [check for check in checks if check.get("required")]
    completed_required = [check for check in required if check.get("completed")]
    optional = [check for check in checks if not check.get("required")]
    completed_optional = [check for check in optional if check.get("completed")]
    required_percent = round((len(completed_required) / max(len(required), 1)) * 100)
    overall_percent = round(((len(completed_required) + len(completed_optional)) / max(len(checks), 1)) * 100)
    can_publish = len(completed_required) == len(required)
    return {
        "profileCode": profile_code,
        "requiredPercent": required_percent,
        "overallPercent": overall_percent,
        "requiredComplete": len(completed_required),
        "requiredTotal": len(required),
        "optionalComplete": len(completed_optional),
        "optionalTotal": len(optional),
        "canPublish": can_publish,
        "websiteStatus": tenant.get("websiteStatus", "not_generated"),
        "tenantStatus": tenant.get("status", "draft"),
        "status": "published" if tenant.get("websiteStatus") == "published" else ("ready_to_publish" if can_publish else "needs_setup"),
    }


async def get_launch_status(tenant_id: str, user: dict) -> dict:
    _, tenant, category, context = await _load_launch_context(tenant_id, user)
    checks = build_launch_checks(tenant, category, context["enabled"], context["counts"])
    phase28 = (((tenant.get("settings") or {}).get("onboarding") or {}).get("phase28") or {})
    profile_code = normalize_launch_profile(phase28.get("profileCode"))
    profiles = {
        code: {
            **profile,
            "accessStatus": _profile_access_status(tenant, profile),
            "targetPlanName": get_plan_definition(profile["targetPlan"])["name"],
            "targetPlanDisplayName": get_plan_definition(profile["targetPlan"])["displayName"],
        }
        for code, profile in LAUNCH_PROFILES.items()
    }
    return {
        "tenant": serialize_document(tenant),
        "category": serialize_document(category) if category else {},
        "profiles": profiles,
        "checks": checks,
        "summary": summarize_launch_status(checks, tenant, profile_code),
        "counts": context["counts"],
        "modules": context["modules"],
    }


async def _set_tenant_plan(tenant_oid: ObjectId, plan_code: str, user: dict) -> None:
    db = get_database()
    tenant = await db.tenants.find_one({"_id": tenant_oid})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    settings = dict(tenant.get("settings") or {})
    settings["planCode"] = plan_code
    await db.tenants.update_one(
        {"_id": tenant_oid},
        {"$set": {"settings": settings, "updatedAt": datetime.now(timezone.utc)}},
    )
    await db.audit_logs.insert_one(
        {
            "action": "tenant_launch_plan_updated",
            "actorUserId": user.get("_id"),
            "tenantId": tenant_oid,
            "metadata": {"planCode": plan_code},
            "createdAt": datetime.now(timezone.utc),
        }
    )


async def _bootstrap_launch_defaults(tenant_oid: ObjectId, tenant: dict, category: dict, profile_code: str, modules: list[str], user: dict) -> dict[str, Any]:
    db = get_database()
    now = datetime.now(timezone.utc)
    bootstrapped: dict[str, Any] = {"websiteSettings": False, "paymentSettings": False, "reportSettings": False, "whatsappIntegration": False}

    tenant_update: dict[str, Any] = {"updatedAt": now}
    if "website_builder" in modules and not (tenant.get("websiteSettings") or {}).get("templateCode"):
        tenant_update["websiteSettings"] = _launch_website_settings(tenant, category)
        bootstrapped["websiteSettings"] = True

    if "payments" in modules and not await db.payment_settings.find_one({"tenantId": tenant_oid}):
        await db.payment_settings.insert_one({**build_launch_payment_defaults(tenant_oid, user.get("_id")), "createdAt": now, "updatedAt": now})
        bootstrapped["paymentSettings"] = True

    if "reports" in modules and not await db.report_delivery_settings.find_one({"tenantId": tenant_oid}):
        await db.report_delivery_settings.insert_one({**build_launch_report_defaults(tenant_oid, tenant), "createdAt": now, "updatedAt": now})
        bootstrapped["reportSettings"] = True

    if "whatsapp_agent" in modules and not await db.whatsapp_integrations.find_one({"tenantId": tenant_oid}):
        await db.whatsapp_integrations.insert_one({**build_launch_whatsapp_defaults(tenant_oid, tenant), "createdAt": now, "updatedAt": now})
        bootstrapped["whatsappIntegration"] = True

    tenant_update["settings.onboarding.phase28.bootstrapDefaults"] = bootstrapped
    tenant_update["settings.onboarding.phase28.bootstrapProfileCode"] = profile_code
    tenant_update["settings.onboarding.phase28.bootstrapAt"] = now.isoformat()
    await db.tenants.update_one({"_id": tenant_oid}, {"$set": tenant_update})
    return bootstrapped


async def apply_launch_profile(tenant_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant, category, context = await _load_launch_context(tenant_id, user)
    profile_code = normalize_launch_profile(payload.profileCode)
    profile = LAUNCH_PROFILES[profile_code]
    current_plan = ((tenant.get("settings") or {}).get("planCode") or "starter")
    target_plan = highest_required_plan(current_plan, profile.get("targetPlan"))
    if profile.get("isPaid") and not _is_platform_admin(user) and _profile_access_status(tenant, profile) != "approved":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{profile['name']} is a paid package. Please complete payment or request admin approval before applying it.",
        )

    if target_plan != current_plan:
        if not payload.autoUpgradePlan:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"This launch profile needs the {target_plan} plan. Enable autoUpgradePlan or choose a smaller profile.",
            )
        await _set_tenant_plan(tenant_oid, target_plan, user)

    enabled_before = set(context["enabled"])
    enabled_now = []
    skipped = []
    errors = []
    for module_code in profile["modules"]:
        if module_code in enabled_before:
            continue
        try:
            await enable_tenant_module(tenant_id, module_code, user)
            enabled_now.append(module_code)
            enabled_before.add(module_code)
        except HTTPException as exc:
            skipped.append(module_code)
            errors.append({"moduleCode": module_code, "detail": exc.detail, "statusCode": exc.status_code})

    applied_at = datetime.now(timezone.utc)
    bootstrapped_defaults = await _bootstrap_launch_defaults(tenant_oid, tenant, category, profile_code, profile["modules"], user)

    await db.tenants.update_one(
        {"_id": tenant_oid},
        {
            "$set": {
                "settings.onboarding.phase28": {
                    "profileCode": profile_code,
                    "profileName": profile["name"],
                    "targetPlan": target_plan,
                    "lastAppliedAt": applied_at.isoformat(),
                    "enabledModules": enabled_now,
                    "skippedModules": skipped,
                    "bootstrapDefaults": bootstrapped_defaults,
                    "bootstrapProfileCode": profile_code,
                    "bootstrapAt": applied_at.isoformat(),
                },
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    await db.audit_logs.insert_one(
        {
            "action": "tenant_launch_profile_applied",
            "actorUserId": user.get("_id"),
            "tenantId": tenant_oid,
            "metadata": {"profileCode": profile_code, "targetPlan": target_plan, "enabledModules": enabled_now, "skippedModules": skipped},
            "createdAt": datetime.now(timezone.utc),
        }
    )
    status_report = await get_launch_status(tenant_id, user)
    status_report["appliedProfile"] = {
        "code": profile_code,
        "name": profile["name"],
        "targetPlan": target_plan,
        "enabledModules": enabled_now,
        "skippedModules": skipped,
        "bootstrappedDefaults": bootstrapped_defaults,
        "errors": errors,
    }
    return status_report


async def request_package_upgrade(tenant_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant, _, _ = await _load_launch_context(tenant_id, user)
    profile_code = normalize_launch_profile(payload.profileCode)
    profile = LAUNCH_PROFILES[profile_code]
    if not profile.get("isPaid"):
        return await apply_launch_profile(tenant_id, payload, user)

    now = datetime.now(timezone.utc)
    settings = dict(tenant.get("settings") or {})
    package_access = dict(settings.get("packageAccess") or {})
    package_access[profile["targetPlan"]] = {
        **(package_access.get(profile["targetPlan"]) or {}),
        "status": "pending_approval",
        "profileCode": profile_code,
        "requestedAt": now.isoformat(),
        "requestedBy": str(user.get("_id")),
        "paymentMode": "mock_manual",
    }
    settings["packageAccess"] = package_access
    settings.setdefault("onboarding", {}).setdefault("phase28", {})
    settings["onboarding"]["phase28"].update(
        {
            "profileCode": profile_code,
            "profileName": profile["name"],
            "targetPlan": profile["targetPlan"],
            "upgradeStatus": "pending_approval",
            "upgradeRequestedAt": now.isoformat(),
        }
    )
    await db.tenants.update_one({"_id": tenant_oid}, {"$set": {"settings": settings, "updatedAt": now}})
    await db.audit_logs.insert_one(
        {
            "action": "tenant_package_upgrade_requested",
            "actorUserId": user.get("_id"),
            "tenantId": tenant_oid,
            "metadata": {"profileCode": profile_code, "targetPlan": profile["targetPlan"], "status": "pending_approval"},
            "createdAt": now,
        }
    )
    report = await get_launch_status(tenant_id, user)
    report["upgradeRequest"] = {
        "profileCode": profile_code,
        "targetPlan": profile["targetPlan"],
        "status": "pending_approval",
        "message": f"{profile['name']} upgrade requested. Admin approval or payment confirmation is required before paid modules unlock.",
    }
    return report


async def finalize_launch(tenant_id: str, payload, user: dict) -> dict:
    status_report = await get_launch_status(tenant_id, user)
    blocking_checks = [check for check in status_report["checks"] if check.get("required") and not check.get("completed")]
    if blocking_checks and not payload.allowWarnings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete the required launch checklist before finalizing.",
        )

    published_tenant = status_report["tenant"]
    publish_error = None
    if payload.publishWebsite:
        try:
            published_tenant = await publish_tenant(tenant_id, user)
        except HTTPException as exc:
            publish_error = {"statusCode": exc.status_code, "detail": exc.detail}
            if not payload.allowWarnings:
                raise

    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await db.tenants.update_one(
        {"_id": tenant_oid},
        {
            "$set": {
                "settings.onboarding.phase28.finalizedAt": datetime.now(timezone.utc).isoformat(),
                "settings.onboarding.phase28.finalizeStatus": "published" if not publish_error and payload.publishWebsite else "saved_with_warnings",
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    next_report = await get_launch_status(tenant_id, user)
    next_report["finalized"] = {
        "publishRequested": payload.publishWebsite,
        "publishError": publish_error,
        "blockingChecks": blocking_checks,
        "tenant": published_tenant,
    }
    return next_report
