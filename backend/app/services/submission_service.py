from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.qa_service import build_phase_summary, build_tenant_qa_report

PHASE_32_TITLE = "Critical Bug Fixes and Flow Stabilization"
SENSITIVE_EXPORT_KEYS = {
    "password",
    "passwordHash",
    "hashedPassword",
    "accessToken",
    "refreshToken",
    "apiKey",
    "secret",
    "secretKey",
    "jwtSecret",
    "webhookSecret",
    "webhookVerifyToken",
    "codeHash",
    "debugCode",
}

ARTIFACT_CHECKLIST = [
    {
        "code": "latest_zip",
        "title": "Latest cleaned project zip",
        "required": True,
        "description": "Submit the latest Phase 32 zip only, not older phase zips.",
    },
    {
        "code": "proposal_pdf",
        "title": "Approved proposal PDF",
        "required": True,
        "description": "Keep the proposal with the final project package for evaluation mapping.",
    },
    {
        "code": "demo_guide",
        "title": "Demo guide and supervisor script",
        "required": True,
        "description": "Use docs/demo-guide.md and docs/supervisor-demo-script.md during viva/demo.",
    },
    {
        "code": "env_example",
        "title": "Environment template only",
        "required": True,
        "description": "Submit .env.example, but never submit a real .env file with secrets.",
    },
    {
        "code": "seed_demo_data",
        "title": "Demo seed and test commands",
        "required": True,
        "description": "Include seed_demo_data.py, smoke_check.py, and final test/build commands.",
    },
    {
        "code": "screenshots_optional",
        "title": "Screenshots or short demo video",
        "required": False,
        "description": "Optional but useful proof for dashboard, WhatsApp mock, RAG upload, and customer order agent.",
    },
]

FILES_TO_SUBMIT = [
    "backend/app/",
    "backend/scripts/",
    "backend/tests/",
    "backend/requirements.txt",
    "backend/.env.example",
    "frontend/src/",
    "frontend/package.json",
    "frontend/vite.config.js",
    "docs/",
    "docker-compose.yml",
    "README.md",
]

FILES_TO_EXCLUDE = [
    ".env",
    "node_modules/",
    "__pycache__/",
    ".pytest_cache/",
    "logs/",
    "uploads/",
    "chroma-data/",
    "test-results/",
    "*.pyc",
]

PROPOSAL_TRACEABILITY = [
    {
        "proposalArea": "Phone-first onboarding",
        "implementedBy": "Phase 29",
        "qaCode": "phone_otp",
        "evidenceRoute": "/login",
    },
    {
        "proposalArea": "Excel/catalog upload and generalized business data",
        "implementedBy": "Phases 8, 21, 24",
        "qaCode": "catalog_ready",
        "evidenceRoute": "/dashboard/items/import",
    },
    {
        "proposalArea": "Automatic website launch",
        "implementedBy": "Phases 10 and 28",
        "qaCode": "website_published",
        "evidenceRoute": "/dashboard/launch-wizard",
    },
    {
        "proposalArea": "Owner knowledge base into RAG",
        "implementedBy": "Phase 21",
        "qaCode": "knowledge_rag",
        "evidenceRoute": "/dashboard/knowledge-base",
    },
    {
        "proposalArea": "Customer AI chatbot can answer and order items",
        "implementedBy": "Phases 23 and 24",
        "qaCode": "customer_agent_ordering",
        "evidenceRoute": "/customer/marketplace",
    },
    {
        "proposalArea": "WhatsApp agent replaces manual query handling",
        "implementedBy": "Phase 22",
        "qaCode": "whatsapp_agent",
        "evidenceRoute": "/dashboard/whatsapp-agent",
    },
    {
        "proposalArea": "Stock-aware ordering and local payments",
        "implementedBy": "Phase 25",
        "qaCode": "stock_and_payments",
        "evidenceRoute": "/dashboard/payments",
    },
    {
        "proposalArea": "Daily reports and owner-side AI assistant",
        "implementedBy": "Phase 26",
        "qaCode": "reports_owner_agent",
        "evidenceRoute": "/dashboard/owner-agent",
    },
    {
        "proposalArea": "Final hardening, testing, and viva demo",
        "implementedBy": "Phases 27, 30, 31, 32",
        "qaCode": "demo_data_and_qa",
        "evidenceRoute": "/dashboard/final-qa",
    },
]


def normalize_submission_status(value: str | None) -> str:
    normalized = str(value or "ready").strip().lower()
    if normalized not in {"ready", "ready_with_notes", "blocked"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Submission status must be ready, ready_with_notes, or blocked.")
    return normalized


def required_artifact_codes() -> set[str]:
    return {artifact["code"] for artifact in ARTIFACT_CHECKLIST if artifact.get("required")}


def normalize_included_artifacts(values: list[str] | None) -> list[str]:
    valid = {artifact["code"] for artifact in ARTIFACT_CHECKLIST}
    normalized: list[str] = []
    for value in values or []:
        code = str(value or "").strip()
        if code in valid and code not in normalized:
            normalized.append(code)
    return normalized


def build_artifact_summary(included_artifacts: list[str] | None) -> dict[str, Any]:
    included = normalize_included_artifacts(included_artifacts)
    required = required_artifact_codes()
    missing_required = sorted(required.difference(included))
    return {
        "includedArtifacts": included,
        "requiredArtifacts": sorted(required),
        "missingRequiredArtifacts": missing_required,
        "requiredComplete": len(missing_required) == 0,
        "includedCount": len(included),
        "requiredCount": len(required),
    }


def build_submission_summary(qa_summary: dict[str, Any], signoff: dict[str, Any] | None = None) -> dict[str, Any]:
    required_percent = int(qa_summary.get("requiredPercent") or 0)
    overall_percent = int(qa_summary.get("percent") or 0)
    blocking = qa_summary.get("blockingGaps") or []
    warnings = qa_summary.get("warnings") or []
    artifact_summary = build_artifact_summary((signoff or {}).get("includedArtifacts") or [])
    signed = bool(signoff and signoff.get("status") in {"ready", "ready_with_notes"} and artifact_summary["requiredComplete"])

    if blocking:
        status_value = "not_ready"
    elif required_percent >= 90 and signed:
        status_value = "submission_ready"
    elif required_percent >= 90:
        status_value = "ready_needs_signoff"
    else:
        status_value = "needs_review"

    return {
        "status": status_value,
        "requiredPercent": required_percent,
        "overallPercent": overall_percent,
        "blockingCount": len(blocking),
        "warningCount": len(warnings),
        "signedOff": signed,
        "latestSignoffStatus": signoff.get("status") if signoff else "not_signed",
        "artifactSummary": artifact_summary,
    }


def build_public_submission_summary() -> dict[str, Any]:
    phase_summary = build_phase_summary()
    return {
        "appVersion": settings.app_version,
        "buildLabel": settings.build_label,
        "implementedThrough": 32,
        "latestPhase": PHASE_32_TITLE,
        "headline": "BizXusAI includes all proposal-critical modules plus stabilized ordering, AI matching, OTP, file upload, and final submission/evidence support.",
        "phases": phase_summary.get("phaseSummary", []),
        "artifactChecklist": ARTIFACT_CHECKLIST,
        "filesToExclude": FILES_TO_EXCLUDE,
    }


def _traceability_with_status(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_code = {check.get("code"): check for check in checks}
    rows = []
    for row in PROPOSAL_TRACEABILITY:
        check = by_code.get(row["qaCode"], {})
        rows.append({
            **row,
            "status": check.get("status", "warn"),
            "evidence": check.get("evidence", {}),
            "description": check.get("description", ""),
        })
    return rows


async def _collection_count_summary(tenant_oid: ObjectId) -> dict[str, int]:
    db = get_database()
    return {
        "items": await db.items.count_documents({"tenantId": tenant_oid}),
        "activeItems": await db.items.count_documents({"tenantId": tenant_oid, "status": "active"}),
        "customers": await db.customers.count_documents({"tenantId": tenant_oid}),
        "transactions": await db.transactions.count_documents({"tenantId": tenant_oid}),
        "knowledgeDocuments": await db.knowledge_documents.count_documents({"tenantId": tenant_oid}),
        "activeKnowledgeDocuments": await db.knowledge_documents.count_documents({"tenantId": tenant_oid, "isActive": True}),
        "conversations": await db.conversations.count_documents({"tenantId": tenant_oid}),
        "whatsappConversations": await db.conversations.count_documents({"tenantId": tenant_oid, "channel": "whatsapp"}),
        "paymentRecords": await db.payment_records.count_documents({"tenantId": tenant_oid}),
        "inventoryMovements": await db.inventory_movements.count_documents({"tenantId": tenant_oid}),
        "reportDeliveryLogs": await db.report_delivery_logs.count_documents({"tenantId": tenant_oid}),
        "qaDemoRuns": await db.qa_demo_runs.count_documents({"tenantId": tenant_oid}),
        "submissionSignoffs": await db.submission_signoffs.count_documents({"tenantId": tenant_oid}),
    }


async def build_submission_package(tenant_id: str, user: dict) -> dict[str, Any]:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    qa_report = await build_tenant_qa_report(tenant_id, user)
    latest_signoff = await db.submission_signoffs.find_one({"tenantId": tenant_oid}, sort=[("createdAt", -1)])
    counts = await _collection_count_summary(tenant_oid)
    summary = build_submission_summary(qa_report.get("summary") or {}, latest_signoff)

    return {
        "tenant": serialize_document(tenant),
        "summary": summary,
        "phaseSummary": build_public_submission_summary(),
        "proposalTraceability": _traceability_with_status(qa_report.get("checks") or []),
        "artifactChecklist": ARTIFACT_CHECKLIST,
        "filesToSubmit": FILES_TO_SUBMIT,
        "filesToExclude": FILES_TO_EXCLUDE,
        "counts": counts,
        "qaSummary": qa_report.get("summary"),
        "latestQaRun": qa_report.get("latestDemoRun"),
        "latestSignoff": serialize_document(latest_signoff),
        "finalCommands": qa_report.get("commands") or [],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


async def record_submission_signoff(tenant_id: str, payload, user: dict) -> dict[str, Any]:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)
    now = datetime.now(timezone.utc)
    package = await build_submission_package(tenant_id, user)
    included_artifacts = normalize_included_artifacts(payload.includedArtifacts or [])
    artifact_summary = build_artifact_summary(included_artifacts)
    signoff_status = normalize_submission_status(payload.status)
    if signoff_status in {"ready", "ready_with_notes"} and not artifact_summary["requiredComplete"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Required artifacts are missing before sign-off: {', '.join(artifact_summary['missingRequiredArtifacts'])}.",
        )
    record = {
        "tenantId": tenant_oid,
        "status": signoff_status,
        "reviewerName": str(payload.reviewerName or user.get("fullName") or "Business owner").strip(),
        "notes": str(payload.notes or "").strip(),
        "includedArtifacts": included_artifacts,
        "artifactSummary": artifact_summary,
        "submissionSummary": package.get("summary") or {},
        "qaSummary": package.get("qaSummary") or {},
        "createdBy": user["_id"],
        "createdAt": now,
    }
    record["_id"] = (await db.submission_signoffs.insert_one(record)).inserted_id
    return serialize_document(record)


def _safe_document(document: dict | None) -> dict | None:
    if not document:
        return None
    return sanitize_export_value(serialize_document(document) or {})


def sanitize_export_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, nested in value.items():
            if str(key) in SENSITIVE_EXPORT_KEYS or any(token in str(key).lower() for token in ["token", "secret", "password", "hash"]):
                sanitized[key] = "[removed]"
            else:
                sanitized[key] = sanitize_export_value(nested)
        return sanitized
    if isinstance(value, list):
        return [sanitize_export_value(item) for item in value]
    return value


async def _limited_collection_snapshot(collection_name: str, tenant_oid: ObjectId, limit: int = 20, projection: dict | None = None) -> list[dict[str, Any]]:
    db = get_database()
    collection = getattr(db, collection_name)
    cursor = collection.find({"tenantId": tenant_oid}, projection or {}).sort("createdAt", -1).limit(limit)
    return [_safe_document(doc) for doc in await cursor.to_list(length=limit)]


async def build_tenant_export_snapshot(tenant_id: str, user: dict) -> dict[str, Any]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    package = await build_submission_package(tenant_id, user)
    return {
        "exportType": "bizxusai_phase32_tenant_submission_snapshot",
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "tenant": _safe_document(tenant),
        "submissionPackage": package,
        "collections": {
            "items": await _limited_collection_snapshot("items", tenant_oid, projection={"name": 1, "status": 1, "itemType": 1, "price": 1, "stock": 1, "variants": 1, "createdAt": 1, "updatedAt": 1}),
            "knowledgeDocuments": await _limited_collection_snapshot("knowledge_documents", tenant_oid, projection={"title": 1, "sourceType": 1, "isActive": 1, "moduleCode": 1, "tags": 1, "createdAt": 1, "updatedAt": 1}),
            "transactions": await _limited_collection_snapshot("transactions", tenant_oid, projection={"transactionNumber": 1, "transactionType": 1, "status": 1, "workflowStatus": 1, "paymentStatus": 1, "totalAmount": 1, "items": 1, "createdAt": 1}),
            "conversations": await _limited_collection_snapshot("conversations", tenant_oid, projection={"channel": 1, "status": 1, "intent": 1, "lastMessageAt": 1, "createdAt": 1}),
            "qaDemoRuns": await _limited_collection_snapshot("qa_demo_runs", tenant_oid),
            "submissionSignoffs": await _limited_collection_snapshot("submission_signoffs", tenant_oid),
        },
        "exportLimits": {"maxDocumentsPerCollection": 20, "secretsRedacted": True},
        "securityNote": "Secrets, tokens, passwords, uploads, logs, node_modules, and vector/runtime data are excluded from the final submission zip.",
    }
