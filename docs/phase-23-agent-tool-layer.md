# Phase 23 — Real Agent Tool Layer

## Goal

Phase 23 converts the previous single AI chat service into a clear, reusable agent/tool architecture. Customer Portal chat, Public Website chat, and WhatsApp Agent now call the same orchestrated brain.

## What was implemented

### Backend

Added a LangGraph-ready agent layer under:

```text
backend/app/ai/agents/
```

Main files:

```text
backend/app/ai/agents/state.py
backend/app/ai/agents/tools.py
backend/app/ai/agents/orchestrator_agent.py
backend/app/schemas/agent_schema.py
backend/app/services/agent_tool_service.py
backend/app/api/v1/agent_routes.py
```

The orchestrator runs these tools in sequence:

```text
1. category_context_loader
2. language_detector
3. safety_guard
4. catalog_search_tool
5. intent_classifier
6. hybrid_rag_retriever
7. draft_order_tool
8. stock_tool
9. payment_tool
10. report_tool
11. notification_tool
12. response_generator
13. localization_evaluator
```

### Existing chat channels updated

These existing channels now use the same agent tool layer:

```text
Customer Portal Chat
Public Website Chat
WhatsApp Agent
Owner Preview / Debug
```

Updated files:

```text
backend/app/services/ai_chat_service.py
backend/app/services/whatsapp_service.py
backend/app/api/v1/router.py
backend/app/db/seeders/seed_modules.py
backend/app/services/rag_index_service.py
```

### Owner dashboard preview

Added an owner-facing Agent Tools page:

```text
/dashboard/agent-tools
```

Frontend files:

```text
frontend/src/features/dashboard/AgentToolsPage.jsx
frontend/src/services/agentApi.js
frontend/src/app/router.jsx
frontend/src/components/layout/DashboardLayout.jsx
```

The owner can test a message like:

```text
2 black shirts order kar do
```

The preview shows:

```text
AI reply
intent
language mode
response source
matched items
RAG sources
draft order
tool-by-tool trace
```

## New API endpoints

```text
GET  /api/v1/tenants/{tenantId}/agent/tools
POST /api/v1/tenants/{tenantId}/agent/preview
```

Example preview payload:

```json
{
  "messageText": "2 black shirts order kar do",
  "channel": "owner_preview"
}
```

## Catalog and variant improvements

The catalog search tool now searches more than item names:

```text
item name
description
tags
custom fields
variant names
variant SKU
variant option values such as color, size, material
```

Draft orders can now include variant-aware details:

```text
selectedVariantIndex
selectedVariantName
selectedOptions
variantSku
stockSnapshot
requestedAttributes
```

This prepares the project for Phase 24 customer ordering improvements.

## Operational tool split

The Phase 23 orchestrator now exposes the tool split from the implementation roadmap:

```text
RAG tool: retrieves owner knowledge and tenant profile context
Catalog search tool: matches item names, tags, custom fields, variants, and budgets
Order tool: prepares safe draft orders only
Stock tool: summarizes availability, low-stock risk, and confirmation blockers
Payment tool: explains enabled COD/manual/mock wallet options but never marks paid
Report tool: keeps owner analytics/report context guarded from customer channels
Notification tool: plans notification handoff without sending side effects during preview/chat
```

## Safety improvements

Added a basic safety guard for:

```text
prompt injection attempts
requests to change price/payment/stock through chat
pharmacy dosage/medical-advice style questions
secret/API key requests
```

The agent still answers normal product, price, stock, timing, and order-draft questions.

## Important note

This phase is intentionally LangGraph-ready, but it does not require LangGraph as a dependency yet. The current implementation is deterministic and easier for FYP testing. If LangGraph is added later, each tool in `orchestrator_agent.py` can become a LangGraph node without changing the customer-facing APIs.

## Acceptance checklist

- [x] Agent tool files added.
- [x] Existing chat routes use the orchestrator.
- [x] WhatsApp agent uses the orchestrator.
- [x] Owner can preview an agent run.
- [x] Tool trace is visible in dashboard.
- [x] RAG sources are returned.
- [x] Draft order tool returns variant-aware draft lines.
- [x] Stock/payment/report/notification tools are exposed in the trace.
- [x] Safety guard added.
- [x] Backend compile check passes.
- [x] Frontend production build passes.
