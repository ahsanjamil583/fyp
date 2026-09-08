from __future__ import annotations

from typing import Any

from app.ai.agents.state import AgentRunState
from app.core.item_views import customer_stock_snapshot
from app.ai.agents.tools import (
    build_agent_meta,
    build_draft_order,
    build_rag_sources,
    classify_message_intent,
    clean_customer_reply,
    detect_language_mode,
    generate_agent_response,
    hydrate_tenant_category,
    OWNER_CHANNELS,
    rank_matching_items,
    retrieve_sellable_items,
    retrieve_tenant_knowledge,
    run_safety_guard,
    select_catalog_for_prompt,
    summarize_notification_tool,
    summarize_payment_tool,
    summarize_report_tool,
    summarize_stock_tool,
)
from app.services.localization_service import evaluate_localized_reply
from app.services.phase32_utils import is_short_confirmation


def _safe_item_summary(item: dict[str, Any]) -> dict[str, Any]:
    variant = item.get("agentMatchedVariant") or None
    return {
        "id": str(item.get("_id", item.get("id", ""))),
        "name": item.get("name", ""),
        "itemType": item.get("itemType", ""),
        "price": float(item.get("price", 0) or 0),
        "currency": item.get("currency", "PKR"),
        "matchScore": item.get("agentMatchScore", 0),
        "matchedVariant": variant,
    }


async def run_customer_agent(
    tenant: dict[str, Any],
    user_message: str,
    recent_messages: list[dict[str, Any]] | None = None,
    *,
    channel: str = "customer_portal",
) -> dict[str, Any]:
    """Run the phase-23 agent tool layer.

    This is a deterministic, LangGraph-ready orchestration layer. It separates
    the previous single-service AI flow into explicit tools/agents:
    language, safety, catalog, intent, RAG, draft planning, and response.
    The output contract stays compatible with existing customer portal,
    public website chat, and WhatsApp integrations.
    """

    recent_messages = recent_messages or []
    effective_message = user_message
    if is_short_confirmation(user_message):
        previous_customer_messages = [message.get("messageText", "") for message in recent_messages[:-1] if message.get("sender") == "customer"]
        if previous_customer_messages:
            effective_message = f"{previous_customer_messages[-1]} {user_message}"

    state = AgentRunState(tenant=tenant, userMessage=user_message, recentMessages=recent_messages, channel=channel)

    state.tenant = await hydrate_tenant_category(state.tenant)
    state.add_event(
        agent="orchestrator_agent",
        tool="category_context_loader",
        summary="Loaded category configuration for this tenant.",
        output_data={"category": (state.tenant.get("categoryConfig") or {}).get("name", "")},
    )

    state.languageMode = detect_language_mode(user_message)
    state.add_event(
        agent="language_agent",
        tool="language_detector",
        summary="Detected customer language mode.",
        input_data={"messageLength": len(user_message)},
        output_data={"languageMode": state.languageMode},
    )

    state.safety = run_safety_guard(effective_message, state.tenant)
    state.add_event(
        agent="safety_agent",
        tool="safety_guard",
        summary="Checked operational and prompt-safety rules.",
        output_data={"allowed": state.safety.get("allowed", True), "flags": state.safety.get("flags", {})},
    )

    state.items = await retrieve_sellable_items(state.tenant)
    state.matchedItems = rank_matching_items(effective_message, state.items)
    state.add_event(
        agent="catalog_agent",
        tool="catalog_search_tool",
        summary="Searched catalog items, custom fields, tags, variants, budget, and attribute matches.",
        input_data={"sellableItemCount": len(state.items)},
        output_data={"matchedItemCount": len(state.matchedItems), "matches": [_safe_item_summary(item) for item in state.matchedItems[:5]]},
    )

    state.intentProfile = classify_message_intent(effective_message, state.matchedItems)
    state.add_event(
        agent="intent_agent",
        tool="intent_classifier",
        summary="Classified customer intent.",
        output_data={
            "intent": state.intentProfile.get("intent"),
            "confidence": state.intentProfile.get("confidence"),
            "requestedAttributes": state.intentProfile.get("requestedAttributes") or {},
        },
    )

    state.knowledgeDocs = await retrieve_tenant_knowledge(state.tenant, effective_message, state.intentProfile)
    state.add_event(
        agent="rag_agent",
        tool="hybrid_rag_retriever",
        summary="Retrieved tenant knowledge from RAG.",
        output_data={
            "knowledgeCount": len(state.knowledgeDocs),
            "topConfidence": state.knowledgeDocs[0].get("confidence", 0) if state.knowledgeDocs else 0,
            "sources": [doc.get("title", "Knowledge") for doc in state.knowledgeDocs[:3]],
        },
    )

    state.draftOrder = build_draft_order(state.tenant, effective_message, state.matchedItems, state.intentProfile)
    if state.channel not in OWNER_CHANNELS:
        # Draft lines are echoed straight back to the customer, so the availability
        # snapshot must not carry exact on-hand quantities.
        for line in state.draftOrder.get("items", []):
            line["stockSnapshot"] = customer_stock_snapshot(line.get("stockSnapshot"))
    state.add_event(
        agent="order_agent",
        tool="draft_order_tool",
        summary="Prepared smart draft order with selected variants, stock snapshot, fulfillment preference, and confirmation readiness.",
        output_data={
            "draftReady": bool(state.draftOrder.get("items")),
            "transactionType": state.draftOrder.get("transactionType", ""),
            "lineCount": len(state.draftOrder.get("items", [])),
            "canConfirm": state.draftOrder.get("canConfirm", False),
            "issues": state.draftOrder.get("confirmationIssues", []),
        },
    )

    stock_summary = summarize_stock_tool(state.draftOrder, state.matchedItems)
    state.add_event(
        agent="stock_agent",
        tool="stock_tool",
        summary="Checked draft-order stock availability, low-stock risk, and confirmation blockers.",
        output_data=stock_summary,
    )

    payment_summary = summarize_payment_tool(state.tenant, state.draftOrder)
    state.add_event(
        agent="payment_agent",
        tool="payment_tool",
        summary="Prepared safe payment context without collecting or marking payments in chat.",
        output_data=payment_summary,
    )

    report_summary = summarize_report_tool(state.channel, state.intentProfile)
    state.add_event(
        agent="report_agent",
        tool="report_tool",
        summary="Guarded owner-only report/analytics context for this channel.",
        status="success" if report_summary.get("availableInThisChannel") else "skipped",
        output_data=report_summary,
    )

    notification_summary = summarize_notification_tool(state.channel, state.draftOrder)
    state.add_event(
        agent="notification_agent",
        tool="notification_tool",
        summary="Planned notification handoff for confirmed orders without sending side effects during chat.",
        output_data=notification_summary,
    )

    state.replyText, state.responseSource = await generate_agent_response(
        state.tenant,
        user_message,
        state.recentMessages,
        state.languageMode,
        state.intentProfile,
        state.knowledgeDocs,
        state.draftOrder,
        state.matchedItems,
        state.safety,
        all_items=state.items,
        channel=state.channel,
    )
    state.replyText = clean_customer_reply(state.replyText, state.channel)
    catalog_items = select_catalog_for_prompt(state.matchedItems, state.items, state.intentProfile)
    state.add_event(
        agent="response_agent",
        tool="response_generator",
        summary="Generated final customer-safe answer.",
        output_data={
            "provider": state.responseSource,
            "replyLength": len(state.replyText),
            "catalogItemsInPrompt": len(catalog_items),
        },
    )

    state.localizationEval = evaluate_localized_reply(
        user_message,
        state.replyText,
        state.languageMode,
        state.intentProfile.get("intent", "general_info"),
    )
    state.add_event(
        agent="localization_agent",
        tool="localization_evaluator",
        summary="Checked whether reply matches customer language mode.",
        output_data={"score": state.localizationEval.get("score", 0), "passed": state.localizationEval.get("passed", False)},
    )

    state.meta = build_agent_meta(
        intent_profile=state.intentProfile,
        language_mode=state.languageMode,
        response_source=state.responseSource,
        knowledge_docs=state.knowledgeDocs,
        localization_eval=state.localizationEval,
        safety=state.safety,
        matched_items=state.matchedItems,
    )

    return {
        "reply": state.replyText,
        "draftOrder": state.draftOrder,
        "ragSources": build_rag_sources(state.knowledgeDocs),
        "toolCalls": [event.to_dict() for event in state.toolEvents],
        "meta": state.meta,
        "matches": [_safe_item_summary(item) for item in state.matchedItems[:5]],
    }


AGENT_TOOL_CATALOG = [
    {
        "agent": "orchestrator_agent",
        "tool": "category_context_loader",
        "purpose": "Hydrates the tenant with category-specific AI, fulfillment, and safety context.",
        "input": ["tenant"],
        "output": ["categoryConfig"],
    },
    {
        "agent": "language_agent",
        "tool": "language_detector",
        "purpose": "Detects English, Roman Urdu, or mixed customer language.",
        "input": ["messageText"],
        "output": ["languageMode"],
    },
    {
        "agent": "safety_agent",
        "tool": "safety_guard",
        "purpose": "Blocks prompt injection and applies category-specific safety constraints.",
        "input": ["messageText", "categoryConfig"],
        "output": ["safetyFlags", "allowed"],
    },
    {
        "agent": "catalog_agent",
        "tool": "catalog_search_tool",
        "purpose": "Searches items, tags, custom fields, variants/options such as color and size, and budget hints.",
        "input": ["messageText", "tenantId"],
        "output": ["matchedItems", "matchedVariant"],
    },
    {
        "agent": "intent_agent",
        "tool": "intent_classifier",
        "purpose": "Classifies place-order, price, availability, recommendation, contact, hours, or general info intents.",
        "input": ["messageText", "matchedItems"],
        "output": ["intent", "confidence", "requestedAttributes"],
    },
    {
        "agent": "rag_agent",
        "tool": "hybrid_rag_retriever",
        "purpose": "Retrieves business profile, catalog, and owner-uploaded knowledge base content.",
        "input": ["messageText", "intent", "tenantId"],
        "output": ["knowledgeDocs", "ragSources"],
    },
    {
        "agent": "order_agent",
        "tool": "draft_order_tool",
        "purpose": "Creates a safe draft order with item, quantity, variant options, fulfillment preference, pricing, and stock confirmation readiness. It never marks payment as paid.",
        "input": ["intent", "matchedItems", "messageText"],
        "output": ["draftOrder"],
    },
    {
        "agent": "stock_agent",
        "tool": "stock_tool",
        "purpose": "Summarizes stock availability, low-stock risk, and confirmation blockers for draft order lines.",
        "input": ["draftOrder", "matchedItems"],
        "output": ["stockSummary"],
    },
    {
        "agent": "payment_agent",
        "tool": "payment_tool",
        "purpose": "Explains enabled COD/manual/mock wallet options while preventing chat from marking payments as paid.",
        "input": ["tenant.paymentSettings", "draftOrder"],
        "output": ["paymentContext"],
    },
    {
        "agent": "report_agent",
        "tool": "report_tool",
        "purpose": "Keeps owner reports/analytics available to owner-side flows and guarded from customer channels.",
        "input": ["channel", "intent"],
        "output": ["reportAccessContext"],
    },
    {
        "agent": "notification_agent",
        "tool": "notification_tool",
        "purpose": "Plans notification handoff for confirmed orders without sending notifications during preview/chat planning.",
        "input": ["channel", "draftOrder"],
        "output": ["notificationPlan"],
    },
    {
        "agent": "response_agent",
        "tool": "response_generator",
        "purpose": "Generates the final customer reply using OpenAI, Groq, or deterministic fallback.",
        "input": ["systemPrompt", "messageText", "recentMessages"],
        "output": ["replyText", "responseSource"],
    },
    {
        "agent": "localization_agent",
        "tool": "localization_evaluator",
        "purpose": "Checks whether the assistant reply is localized to the customer language mode.",
        "input": ["messageText", "replyText", "languageMode"],
        "output": ["localizationScore", "passed"],
    },
]
