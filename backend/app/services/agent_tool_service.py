from __future__ import annotations

from bson import ObjectId
from fastapi import HTTPException, status

from app.ai.agents.orchestrator_agent import AGENT_TOOL_CATALOG, run_customer_agent
from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.schemas.agent_schema import AgentPreviewRequest
from app.services.ai_chat_service import load_conversation_messages


async def _get_tenant_for_agent_tools(tenant_id: str, user: dict) -> tuple[ObjectId, dict]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "ai_chat")
    return tenant_oid, tenant


async def get_agent_tool_catalog(tenant_id: str, user: dict) -> dict:
    _, tenant = await _get_tenant_for_agent_tools(tenant_id, user)
    return {
        "tenant": serialize_document(tenant),
        "mode": "phase_24_smart_customer_ordering",
        "description": "LangGraph-ready agent/tool layer with smart customer ordering, variant selection, stock-aware draft checks, and public/customer confirmation flows.",
        "tools": AGENT_TOOL_CATALOG,
        "channels": ["customer_portal", "website", "whatsapp", "owner_preview"],
    }


async def preview_agent_run(tenant_id: str, payload: AgentPreviewRequest, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _get_tenant_for_agent_tools(tenant_id, user)
    recent_messages = []
    if payload.includeRecentMessages:
        conversation = await db.conversations.find_one({"tenantId": tenant_oid, "channel": "owner_preview", "status": "open"})
        if conversation:
            recent_messages = await load_conversation_messages(conversation["_id"])
    result = await run_customer_agent(tenant, payload.messageText, recent_messages, channel=payload.channel or "owner_preview")
    return {
        "tenant": serialize_document(tenant),
        "reply": result["reply"],
        "draftOrder": serialize_document(result.get("draftOrder") or {}),
        "ragSources": result.get("ragSources", []),
        "toolCalls": result.get("toolCalls", []),
        "meta": result.get("meta", {}),
        "matches": result.get("matches", []),
    }
