from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.module_service import list_tenant_modules

PHASE_SUMMARY = [
    {"phase": 21, "title": "Knowledge Base Manager", "status": "implemented"},
    {"phase": 22, "title": "WhatsApp Agent Integration", "status": "implemented"},
    {"phase": 23, "title": "Agent Tool Layer", "status": "implemented"},
    {"phase": 24, "title": "Smarter Customer Ordering", "status": "implemented"},
    {"phase": 25, "title": "Stock and Payments", "status": "implemented"},
    {"phase": 26, "title": "Owner Agent and Daily Reports", "status": "implemented"},
    {"phase": 27, "title": "Final Hardening", "status": "implemented"},
    {"phase": 28, "title": "Launch Wizard", "status": "implemented"},
    {"phase": 29, "title": "Phone OTP Onboarding", "status": "implemented"},
    {"phase": 30, "title": "Full-System QA and Demo Polish", "status": "implemented"},
    {"phase": 31, "title": "Submission Center and Evidence Pack", "status": "implemented"},
    {"phase": 32, "title": "Critical Bug Fixes and Flow Stabilization", "status": "implemented"},
]

DEMO_SCRIPT = [
    {
        "step": 1,
        "title": "Phone-first business login",
        "route": "/login",
        "goal": "Show the Pakistani phone-first owner login/OTP flow and then enter the dashboard.",
        "expectedResult": "Owner can authenticate and select a business workspace.",
    },
    {
        "step": 2,
        "title": "One-click launch wizard",
        "route": "/dashboard/launch-wizard",
        "goal": "Apply the Full Agent Demo profile and publish the business website.",
        "expectedResult": "Required modules are enabled and launch checklist is ready or clearly lists missing setup.",
    },
    {
        "step": 3,
        "title": "Catalog and variants",
        "route": "/dashboard/items",
        "goal": "Open a product/service and show price, stock, custom fields, variants, and ordering support.",
        "expectedResult": "Catalog data is tenant-specific and available to customer/public pages.",
    },
    {
        "step": 4,
        "title": "Owner knowledge base into RAG",
        "route": "/dashboard/knowledge-base",
        "goal": "Upload or review FAQs/policies and show that active documents are indexed for AI answers.",
        "expectedResult": "Owner-controlled knowledge is visible and can be reindexed.",
    },
    {
        "step": 5,
        "title": "Customer chatbot ordering",
        "route": "/customer/businesses/demo-bazaar/chat",
        "goal": "Ask for an item by color/size/budget, create a draft order, and confirm it.",
        "expectedResult": "Agent finds matching catalog item, checks stock, creates order draft, and confirms safely.",
    },
    {
        "step": 6,
        "title": "WhatsApp agent replacement for manual queries",
        "route": "/dashboard/whatsapp-agent",
        "goal": "Use mock inbound message to prove the AI handles customer WhatsApp questions instead of a human operator.",
        "expectedResult": "Inbound WhatsApp message is stored, answered by the same agent brain, and linked to tenant conversation history.",
    },
    {
        "step": 7,
        "title": "Payments and inventory",
        "route": "/dashboard/payments",
        "goal": "Record COD/manual/local-wallet payment and show stock reservation/deduction state on transactions.",
        "expectedResult": "Payment summary and transaction inventory status update correctly.",
    },
    {
        "step": 8,
        "title": "Owner assistant and daily reports",
        "route": "/dashboard/owner-agent",
        "goal": "Ask for today summary, low stock, pending orders, top items, and promotion ideas.",
        "expectedResult": "Owner assistant summarizes real tenant data; reports can be dry-run/sent from Reports.",
    },
    {
        "step": 9,
        "title": "Final QA dashboard",
        "route": "/dashboard/final-qa",
        "goal": "Show that the system has a clear final checklist, demo script, QA score, and test commands.",
        "expectedResult": "Supervisor can see what is complete, what is warning-only, and how to verify the project.",
    },
]

COMMAND_CHECKS = [
    {
        "name": "Backend compile",
        "command": "cd backend && python -m compileall app tests scripts",
        "purpose": "Catches Python syntax/import issues before demo.",
    },
    {
        "name": "Backend tests",
        "command": "cd backend && python -m unittest discover -s tests -p \"test_*.py\" -v",
        "purpose": "Runs service/API unit coverage for auth, AI, launch, QA, security, and workflows.",
    },
    {
        "name": "Frontend production build",
        "command": "cd frontend && npm install && npm run build",
        "purpose": "Verifies dashboard/customer/public pages compile for deployment.",
    },
    {
        "name": "API smoke check",
        "command": "cd backend && python scripts/smoke_check.py http://localhost:8000/api/v1",
        "purpose": "Checks public health/readiness/phase-summary endpoints on a running server.",
    },
]


def build_phase_summary() -> dict[str, Any]:
    return {
        "appVersion": settings.app_version,
        "buildLabel": settings.build_label,
        "phaseSummary": PHASE_SUMMARY,
        "implementedThrough": 32,
        "headline": "BizXusAI is ready for final local QA, supervisor demo, FYP submission packaging, evidence review, and stabilized bug-fix testing.",
        "recommendedDemoOrder": [step["title"] for step in DEMO_SCRIPT],
    }


def _score_check(code: str, title: str, completed: bool, warning: bool, description: str, route: str = "", required: bool = True, evidence: dict | None = None) -> dict[str, Any]:
    if completed:
        status_value = "pass"
    elif warning or not required:
        status_value = "warn"
    else:
        status_value = "fail"
    return {
        "code": code,
        "title": title,
        "status": status_value,
        "completed": bool(completed),
        "required": bool(required),
        "description": description,
        "route": route,
        "evidence": evidence or {},
    }


def _has_module(enabled: set[str], code: str) -> bool:
    return code in enabled


def _tenant_phone_ready(tenant: dict) -> bool:
    contact = tenant.get("contact") or {}
    return bool(str(contact.get("phone") or tenant.get("phone") or "").strip())


def _phase28_finalized(tenant: dict) -> bool:
    settings = tenant.get("settings") or {}
    onboarding = settings.get("onboarding") or {}
    return bool((onboarding.get("phase28") or {}).get("finalizedAt") or (settings.get("phase28Launch") or {}).get("finalizedAt"))


async def _load_tenant_qa_context(tenant_id: str, user: dict) -> dict[str, Any]:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    module_state = await list_tenant_modules(tenant_id, user)
    enabled = set((module_state.get("tenant") or {}).get("enabledModuleCodes") or tenant.get("enabledModuleCodes") or [])
    counts = {
        "activeItems": await db.items.count_documents({"tenantId": tenant_oid, "status": "active"}),
        "sellableItems": await db.items.count_documents({"tenantId": tenant_oid, "status": "active", "$or": [{"isSellable": True}, {"isBookable": True}]}),
        "variantItems": await db.items.count_documents({"tenantId": tenant_oid, "variants.0": {"$exists": True}}),
        "knowledgeDocuments": await db.knowledge_documents.count_documents({"tenantId": tenant_oid, "isActive": True}),
        "aiConversations": await db.conversations.count_documents({"tenantId": tenant_oid}),
        "whatsappConversations": await db.conversations.count_documents({"tenantId": tenant_oid, "channel": "whatsapp"}),
        "agentToolMessages": await db.messages.count_documents({"tenantId": tenant_oid, "toolCalls.0": {"$exists": True}}),
        "transactions": await db.transactions.count_documents({"tenantId": tenant_oid}),
        "pendingTransactions": await db.transactions.count_documents(
            {
                "tenantId": tenant_oid,
                "$or": [
                    {"workflowStatus": {"$in": ["pending", "new", "draft", "confirmed"]}},
                    {"status": {"$in": ["pending", "new", "draft", "confirmed", "accepted"]}},
                ],
            }
        ),
        "customers": await db.customers.count_documents({"tenantId": tenant_oid}),
        "paymentSettings": await db.payment_settings.count_documents({"tenantId": tenant_oid}),
        "reportSettings": await db.report_delivery_settings.count_documents({"tenantId": tenant_oid}),
        "reportLogs": await db.report_delivery_logs.count_documents({"tenantId": tenant_oid}),
        "whatsappIntegrations": await db.whatsapp_integrations.count_documents({"tenantId": tenant_oid}),
        "whatsappConnected": await db.whatsapp_integrations.count_documents({"tenantId": tenant_oid, "isConnected": True}),
        "ownerAgentMessages": await db.owner_agent_messages.count_documents({"tenantId": tenant_oid}),
        "qaRuns": await db.qa_demo_runs.count_documents({"tenantId": tenant_oid}),
    }
    latest_run = await db.qa_demo_runs.find_one({"tenantId": tenant_oid}, sort=[("createdAt", -1)])
    payment_settings = await db.payment_settings.find_one({"tenantId": tenant_oid}) or {}
    report_settings = await db.report_delivery_settings.find_one({"tenantId": tenant_oid}) or {}
    whatsapp_settings = await db.whatsapp_integrations.find_one({"tenantId": tenant_oid}) or {}
    return {
        "tenantOid": tenant_oid,
        "tenant": tenant,
        "enabled": enabled,
        "counts": counts,
        "paymentSettings": payment_settings,
        "reportSettings": report_settings,
        "whatsappSettings": whatsapp_settings,
        "latestRun": latest_run,
        "moduleState": module_state,
    }


def _build_flow_checks(context: dict[str, Any]) -> list[dict[str, Any]]:
    tenant = context["tenant"]
    enabled = context["enabled"]
    counts = context["counts"]
    payment_settings = context["paymentSettings"] or {}
    report_settings = context["reportSettings"] or {}
    whatsapp_settings = context["whatsappSettings"] or {}

    business_profile_ready = all([
        str(tenant.get("name") or "").strip(),
        tenant.get("businessCategoryId"),
        _tenant_phone_ready(tenant),
    ])
    website_ready = tenant.get("websiteStatus") == "published" or _phase28_finalized(tenant)
    local_payment_enabled = any(bool(payment_settings.get(key)) for key in ["codEnabled", "manualEnabled", "jazzCashEnabled", "easyPaisaEnabled", "bankTransferEnabled"])
    report_delivery_ready = bool(report_settings.get("enabled") or report_settings.get("whatsappEnabled") or report_settings.get("smsEnabled"))
    whatsapp_ready = bool(whatsapp_settings.get("isConnected") or settings.whatsapp_provider == "mock") and _has_module(enabled, "whatsapp_agent")
    plan_code = str(((tenant.get("settings") or {}).get("planCode") or "starter")).lower()
    requires_ai_ordering = plan_code in {"growth", "scale"}
    requires_full_agent = plan_code == "scale"
    required_modules = ["items", "website_builder", "analytics", "notifications"]
    if requires_ai_ordering:
        required_modules.extend(["customer_portal", "ai_chat", "payments"])
    if requires_full_agent:
        required_modules.extend(["whatsapp_agent", "owner_agent", "reports"])

    return [
        _score_check(
            "business_profile",
            "Business profile and category",
            business_profile_ready,
            False,
            "Business has name, category, and phone/contact details for Pakistan-first onboarding.",
            "/dashboard/business",
            evidence={"hasName": bool(tenant.get("name")), "hasCategory": bool(tenant.get("businessCategoryId")), "hasPhone": _tenant_phone_ready(tenant)},
        ),
        _score_check(
            "module_stack",
            "Package modules enabled",
            all(_has_module(enabled, code) for code in required_modules),
            all(_has_module(enabled, code) for code in ["items", "website_builder"]),
            "Required modules match the current package: Basic, AI Ordering, or Full Agent.",
            "/dashboard/modules",
            evidence={"planCode": plan_code, "requiredModules": required_modules, "enabled": sorted(enabled)},
        ),
        _score_check(
            "catalog_ready",
            "Catalog, variants, and ordering data",
            counts["sellableItems"] >= 1,
            counts["activeItems"] >= 1,
            "At least one sellable/bookable item is needed for customer chatbot ordering.",
            "/dashboard/items",
            evidence={"activeItems": counts["activeItems"], "sellableItems": counts["sellableItems"], "variantItems": counts["variantItems"]},
        ),
        _score_check(
            "website_published",
            "Public website launch",
            website_ready,
            tenant.get("websiteStatus") in {"draft", "published"},
            "Public site should be published or launch-finalized before supervisor demo.",
            "/dashboard/launch-wizard",
            evidence={"websiteStatus": tenant.get("websiteStatus"), "tenantStatus": tenant.get("status")},
        ),
        _score_check(
            "knowledge_rag",
            "Owner knowledge base + RAG",
            counts["knowledgeDocuments"] >= 1 and _has_module(enabled, "ai_chat"),
            _has_module(enabled, "ai_chat"),
            "Owner-uploaded knowledge documents should be active so the AI can answer business-specific questions.",
            "/dashboard/knowledge-base",
            required=requires_ai_ordering,
            evidence={"activeKnowledgeDocuments": counts["knowledgeDocuments"]},
        ),
        _score_check(
            "customer_agent_ordering",
            "Customer chatbot order flow",
            _has_module(enabled, "ai_chat") and _has_module(enabled, "customer_portal") and counts["sellableItems"] >= 1,
            _has_module(enabled, "ai_chat") and counts["sellableItems"] >= 1,
            "Customer can log in, ask the chatbot to bring/order an item, receive a draft, and confirm it.",
            "/customer/marketplace",
            required=requires_ai_ordering,
            evidence={"aiConversations": counts["aiConversations"], "transactions": counts["transactions"]},
        ),
        _score_check(
            "agent_tool_layer",
            "Shared agent tool layer",
            _has_module(enabled, "ai_chat") and counts["agentToolMessages"] >= 1,
            _has_module(enabled, "ai_chat"),
            "Customer portal, public website, and WhatsApp should use the same traced agent tools for RAG, catalog search, draft order, stock, payment, report guard, and notifications.",
            "/dashboard/agent-tools",
            required=requires_full_agent,
            evidence={"aiEnabled": _has_module(enabled, "ai_chat"), "messagesWithToolCalls": counts["agentToolMessages"]},
        ),
        _score_check(
            "whatsapp_agent",
            "WhatsApp agent replacement for manual queries",
            whatsapp_ready,
            settings.whatsapp_provider == "mock" and _has_module(enabled, "ai_chat"),
            "Business owner can connect/mock WhatsApp so the AI agent answers customer queries previously handled by a person.",
            "/dashboard/whatsapp-agent",
            required=requires_full_agent,
            evidence={"provider": settings.whatsapp_provider, "integrationRows": counts["whatsappIntegrations"], "connectedRows": counts["whatsappConnected"], "whatsappConversations": counts["whatsappConversations"]},
        ),
        _score_check(
            "stock_and_payments",
            "Stock-aware orders and payments",
            _has_module(enabled, "payments") and counts["paymentSettings"] >= 1 and local_payment_enabled,
            _has_module(enabled, "payments"),
            "COD/manual/JazzCash/EasyPaisa settings and inventory reservation/deduction flow are ready.",
            "/dashboard/payments",
            required=requires_ai_ordering,
            evidence={"paymentSettings": counts["paymentSettings"], "localPaymentEnabled": local_payment_enabled, "transactions": counts["transactions"]},
        ),
        _score_check(
            "reports_owner_agent",
            "Daily reports and owner AI assistant",
            _has_module(enabled, "owner_agent") and _has_module(enabled, "reports") and report_delivery_ready,
            _has_module(enabled, "reports") or _has_module(enabled, "owner_agent"),
            "Owner can receive daily reports and ask business questions like low stock, sales, pending orders, and promotions.",
            "/dashboard/owner-agent",
            required=requires_full_agent,
            evidence={"reportSettings": counts["reportSettings"], "reportLogs": counts["reportLogs"], "ownerAgentMessages": counts["ownerAgentMessages"]},
        ),
        _score_check(
            "phone_otp",
            "Phone-first OTP auth polish",
            settings.otp_code_length >= 4 and settings.otp_expire_minutes >= 1,
            False,
            "Phone OTP login/register/reset is configured for business owners and customers.",
            "/login",
            evidence={"codeLength": settings.otp_code_length, "expiryMinutes": settings.otp_expire_minutes, "demoOtp": settings.otp_demo_code if settings.app_env != "production" else "hidden"},
        ),
        _score_check(
            "demo_data_and_qa",
            "Demo data and recorded QA run",
            counts["qaRuns"] >= 1,
            True,
            "Record at least one manual supervisor demo run after verifying the full flow.",
            "/dashboard/final-qa",
            required=False,
            evidence={"qaRuns": counts["qaRuns"], "latestRun": serialize_document(context.get("latestRun"))},
        ),
    ]


def summarize_qa_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    required = [check for check in checks if check.get("required")]
    required_passed = [check for check in required if check.get("status") == "pass"]
    total = len(checks)
    pass_count = sum(1 for check in checks if check.get("status") == "pass")
    warn_count = sum(1 for check in checks if check.get("status") == "warn")
    fail_count = sum(1 for check in checks if check.get("status") == "fail")
    percent = round((pass_count / total) * 100) if total else 0
    required_percent = round((len(required_passed) / len(required)) * 100) if required else 100
    if fail_count:
        status_value = "needs_fixes"
    elif warn_count:
        status_value = "demo_ready_with_warnings"
    else:
        status_value = "demo_ready"
    return {
        "status": status_value,
        "percent": percent,
        "requiredPercent": required_percent,
        "totals": {"pass": pass_count, "warn": warn_count, "fail": fail_count, "total": total},
        "blockingGaps": [check for check in checks if check.get("status") == "fail" and check.get("required")],
        "warnings": [check for check in checks if check.get("status") == "warn"],
        "nextActions": build_qa_next_actions(checks),
    }


def build_qa_next_actions(checks: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    prioritized = [check for check in checks if check.get("status") == "fail" and check.get("required")]
    prioritized.extend(check for check in checks if check.get("status") == "warn")
    actions = []
    for check in prioritized[:limit]:
        actions.append(
            {
                "code": check.get("code", ""),
                "title": check.get("title", ""),
                "route": check.get("route", ""),
                "status": check.get("status", "warn"),
                "action": f"Open {check.get('route') or 'the related dashboard page'} and resolve: {check.get('description', '')}",
            }
        )
    return actions


def normalize_checked_steps(values: list[int] | None) -> list[int]:
    valid_steps = {step["step"] for step in DEMO_SCRIPT}
    normalized = []
    for value in values or []:
        try:
            step = int(value)
        except Exception:
            continue
        if step in valid_steps and step not in normalized:
            normalized.append(step)
    return sorted(normalized)


def build_demo_run_coverage(checked_steps: list[int] | None) -> dict[str, Any]:
    normalized = normalize_checked_steps(checked_steps)
    total = len(DEMO_SCRIPT)
    percent = round((len(normalized) / total) * 100) if total else 100
    missing = [step for step in DEMO_SCRIPT if step["step"] not in set(normalized)]
    return {
        "checkedSteps": normalized,
        "checkedCount": len(normalized),
        "totalSteps": total,
        "percent": percent,
        "missingSteps": missing,
    }


async def build_tenant_qa_report(tenant_id: str, user: dict) -> dict[str, Any]:
    context = await _load_tenant_qa_context(tenant_id, user)
    checks = _build_flow_checks(context)
    summary = summarize_qa_checks(checks)
    return {
        "tenant": serialize_document(context["tenant"]),
        "summary": summary,
        "checks": checks,
        "demoScript": DEMO_SCRIPT,
        "commands": COMMAND_CHECKS,
        "phaseSummary": build_phase_summary(),
        "latestDemoRun": serialize_document(context.get("latestRun")),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def normalize_demo_result(value: str | None) -> str:
    result = str(value or "pass").strip().lower()
    if result not in {"pass", "warn", "fail"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Demo result must be pass, warn, or fail.")
    return result


async def record_demo_run(tenant_id: str, payload, user: dict) -> dict[str, Any]:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)
    now = datetime.now(timezone.utc)
    report = await build_tenant_qa_report(tenant_id, user)
    record = {
        "tenantId": tenant_oid,
        "result": normalize_demo_result(payload.result),
        "notes": str(payload.notes or "").strip(),
        "reviewerName": str(payload.reviewerName or user.get("fullName") or "Business owner").strip(),
        "checkedSteps": normalize_checked_steps(payload.checkedSteps or []),
        "demoCoverage": build_demo_run_coverage(payload.checkedSteps or []),
        "qaSummary": report["summary"],
        "createdBy": user["_id"],
        "createdAt": now,
    }
    record["_id"] = (await db.qa_demo_runs.insert_one(record)).inserted_id
    return serialize_document(record)
