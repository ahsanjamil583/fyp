# Architecture Decisions

## Application Style

BizxusAI will use a modular multi-tenant monolith.

This keeps the FYP MVP simple enough to build and deploy while preserving clear service boundaries for future scaling.

## Product Shape

BizxusAI is a generalized business platform for Pakistani SMEs.

The product must support any business category through configuration. Restaurant, pharmacy, and retail are seeded demo examples and proposal reference categories, not hardcoded architectural limits.

## Backend

Backend stack:

- Python
- FastAPI
- Pydantic
- MongoDB Atlas
- Motor async MongoDB driver
- JWT authentication
- bcrypt password hashing
- OpenPyXL for Excel imports
- FastAPI BackgroundTasks for small async jobs
- APScheduler only when scheduled summaries are needed
- ChromaDB for RAG
- Groq API for AI responses
- Rule-based fallback chatbot

Decision: use Motor with explicit service-layer database access.

Reason:

- It keeps MongoDB behavior transparent.
- It avoids ODM coupling early in the project.
- It works well with dynamic schemas such as custom fields.
- Pydantic schemas still provide request/response validation.

Development uses local MongoDB. Deployment uses MongoDB Atlas.

## Frontend

Frontend stack:

- React.js
- JavaScript
- Vite
- Tailwind CSS
- React Router
- TanStack Query
- Context API
- React Hook Form
- Joi
- Axios

## Backend Module Boundaries

Planned backend folders:

- `core`: config, security, permissions, tenant context, module guard, errors
- `db`: MongoDB connection, indexes, seeders
- `models`: internal database shape definitions and helpers
- `schemas`: Pydantic request/response schemas
- `api/v1`: route modules
- `services`: business logic
- `ai`: prompts, RAG, fallback chatbot, AI tools
- `integrations`: Groq, ImageKit, Cloudinary, WhatsApp, email, SMS
- `background`: import, RAG, analytics, and notification jobs
- `tests`: unit, integration, e2e

## Frontend Module Boundaries

Planned frontend folders:

- `app`: app shell, router, providers
- `components`: shared UI and layout components
- `features`: route-level feature modules
- `services`: Axios API wrappers
- `context`: auth, customer, tenant, module state
- `utils`: permissions, dynamic forms, validators, formatting, storage

## Data Ownership

Tenant-owned records must include:

- `tenantId`
- `branchId`, set to `null` until branch management is added
- created/updated timestamps where relevant

User-owned customer portal records must include:

- `customerUserId`
- optional `tenantId` when the record belongs to a specific business

## Selected Collections

Only these collections are in scope for the selected phases:

- `users`
- `customer_profiles`
- `tenants`
- `business_categories`
- `modules`
- `tenant_modules`
- `custom_field_definitions`
- `customers`
- `item_categories`
- `items`
- `item_imports`
- `transactions`
- `carts`
- `conversations`
- `messages`
- `knowledge_documents`
- `analytics_daily`
- `payments`
- `reports`
- `notifications`
- `audit_logs`

Future collections such as `memberships`, `roles`, `branches`, `workflows`, `appointments`, `plans`, `subscriptions`, `usage_logs`, `api_keys`, and `webhooks` are intentionally not implemented now.

## Business Category Rule

Business categories must not control backend logic through conditionals.

Allowed:

- suggested modules
- default custom fields
- AI hints
- website template hints
- dashboard suggestions

Not allowed:

- category-specific backend branches such as restaurant-only order logic
- category-specific collections for the MVP

Additional rule:

- categories may influence module suggestions, templates, AI hints, fulfillment hints, analytics hints, and custom-field presets, but they must not fork the core domain model per category

## Generalized Domain Rule

The platform should model shared business primitives instead of category-specific features first.

Preferred shared primitives:

- tenant
- category configuration
- module
- customer
- item or service
- transaction
- public website
- AI conversation
- knowledge document

This allows the same backend to serve restaurants, pharmacies, retail stores, salons, tutors, repair shops, home businesses, and future categories without structural rewrites.

## Order Rule

Frontend and AI may submit item IDs and quantities only.

Backend must recalculate:

- item names copied into the transaction
- unit prices
- subtotals
- discounts
- taxes
- delivery fees
- final total

AI may create only a draft order suggestion. Final order creation requires customer confirmation.

Future-proof note:

- the MVP can remain order-first, but the long-term transaction model should expand to quote requests, booking requests, and inquiry flows without category-specific branching

## Storage Provider Interface

Storage will be accessed through a provider interface so the app can start with ImageKit and still support local development, GridFS, or Cloudinary later.

Planned operations:

- upload public image
- upload temporary import file
- delete file
- build public URL
- store metadata with tenant/user ownership

Primary MVP provider:

- ImageKit

Development fallback:

- local `/uploads` folder where needed

Deployment compatibility:

- keep Cloudinary config fields available because the blueprint includes it in the deployment stack

## ChromaDB RAG Flow

The Phase 14 RAG flow will be prepared around tenant isolation:

1. Tenant profile, FAQ/policy content, and active item data are converted into knowledge documents.
2. Background indexing chunks the content.
3. Chunks are embedded and stored in ChromaDB.
4. Each tenant uses an isolated Chroma collection name such as `tenant_{tenantId}`.
5. Chat retrieves only from the current tenant collection.
6. Retrieved snippets are passed to Groq with a guarded system prompt.
7. If Groq fails or quota is unavailable, the rule-based fallback chatbot responds.
8. AI order suggestions remain drafts until the customer confirms.

Current implementation note:

- prompt-grounded tenant knowledge retrieval is already active through Mongo knowledge documents
- full vector retrieval is not complete until embeddings and live Chroma retrieval are implemented end-to-end

## Customer Marketplace Flow

The marketplace flow will use published tenant data only:

1. Customer registers or logs in.
2. Customer opens marketplace.
3. Backend returns tenants where status is active, website is published, and public visibility is enabled.
4. Customer searches/filter businesses by category and city.
5. Customer opens a business page.
6. Customer views active sellable items/services.
7. Customer adds items to cart or starts AI chat.
8. Backend recalculates prices when an order is placed.
9. Customer sees only their own order history.
10. Business owner sees marketplace orders inside tenant dashboard and analytics.
