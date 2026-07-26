# Supervisor Demo Script

Use this as a speaking script during the final demo.

## 1. Introduction

BizXusAI is a generalized multi-tenant business automation platform for Pakistani SMEs. The proposal started with restaurants, pharmacies, and retail, but the implementation is generalized so any small business can configure its category, modules, items, fields, website, AI assistant, and workflows.

## 2. Problem

Small businesses often do not have websites, online ordering, AI customer support, or technical staff. They also receive many repetitive WhatsApp/customer queries manually.

## 3. Solution

BizXusAI gives the owner:

```text
A business dashboard
A public website
Excel/catalog upload
Knowledge-base upload into RAG
Customer and public chatbot
WhatsApp agent channel
Smart ordering by color/size/budget
Stock-aware transactions
COD/manual/local payment tracking
Daily reports
Owner AI assistant
```

## 4. Technical Architecture

```text
Frontend: React + Tailwind
Backend: FastAPI
Database: MongoDB
RAG: ChromaDB-compatible vector layer
AI Layer: Orchestrator + tools for intent, safety, RAG, catalog search, draft order, and response generation
Integrations: mock WhatsApp/SMS providers for FYP demo, provider seams for real integrations
```

## 5. Key Demo Examples

Customer query:

```text
black hoodie large chahiye delivery ke sath
```

Expected system behavior:

```text
Detect order intent
Extract color = black
Extract size = large
Search catalog and variants
Check stock
Prepare draft order
Ask for confirmation
Create order after confirmation
Reserve/deduct stock according to workflow
```

Owner query:

```text
Which items are low stock?
```

Expected system behavior:

```text
Read inventory
Summarize low-stock items
Suggest reorder action
```

WhatsApp use case:

```text
Customer sends WhatsApp message to business number.
Webhook receives it.
BizXusAI maps it to the business.
The same AI agent answers instead of a human operator.
```

## 6. Final Statement

This implementation now covers the proposal's major goals: generalized website creation, RAG-powered AI answers, smart order handling, WhatsApp-ready automation, owner insights, and deployment readiness.
