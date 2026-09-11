# BizXusAI

BizXusAI is a generalized, multi-tenant SaaS business automation platform for Pakistani SMEs. It combines business onboarding, public websites, catalog management, customer portal, RAG-powered AI chat, WhatsApp agent support, smart ordering, stock/payment management, reports, and an owner-side AI assistant.

The project is implemented phase-wise. The current package includes phases through **Phase 32: Critical Bug Fixes and Flow Stabilization**.

## Current Completion Scope

Implemented in this latest codebase:

```text
Generalized SaaS tenant/business foundation
Business categories and modules
Custom fields engine
Items/services/packages/variants
Excel/catalog import foundation
Public website builder
Customer marketplace and customer portal
Basic AI chat + RAG foundation
Owner knowledge-base upload into RAG
WhatsApp agent integration with mock provider and Meta-ready provider seam
Agent/tool orchestration layer
Smarter customer ordering by color, size, budget, and variants
Stock reservation/deduction/release workflow
Payment settings and manual/COD/local wallet tracking
Daily report delivery settings and dry-run/send-now flow
Owner AI assistant for business insights
Deployment readiness dashboard
Launch Wizard with one-click setup profiles and readiness checklist
Demo data and smoke-check scripts
Docker files for local deployment
Final submission center, proposal traceability, sign-off, and evidence export
```

## Important Demo Accounts

After running the demo seed script:

```text
Business owner: owner@bizxus.demo / Demo@12345
Customer: customer@bizxus.demo / Demo@12345
Admin: admin@bizxus.demo / Admin@12345
Public business: /businesses/demo-bazaar
```

## Quick Local Setup

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload
```

Health checks:

```text
http://localhost:8000/api/v1/health
http://localhost:8000/api/v1/health/readiness
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## Seed Demo Data

Start MongoDB, then run:

```bash
cd backend
python scripts/seed_demo_data.py
```

This creates a complete demo business with modules, items, variants, knowledge base documents, customer, sample order, sample conversation, WhatsApp/report/payment settings, and demo accounts.

## Run Checks

Backend compile:

```bash
cd backend
python -m compileall app tests scripts
```

Backend tests:

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py" -v
```

Frontend build:

```bash
cd frontend
npm run build
```

API smoke check:

```bash
cd backend
python scripts/smoke_check.py http://localhost:8000/api/v1
```

## Docker Local Run

Create `backend/.env` first, then:

```bash
docker compose up --build
```

URLs:

```text
Frontend: http://localhost:5173
Backend: http://localhost:8000/api/v1/health
```

## Key Dashboard Routes

```text
/dashboard/deployment-readiness
/dashboard/final-qa
/dashboard/submission-center
/dashboard/launch-wizard
/dashboard/business
/dashboard/modules
/dashboard/items
/dashboard/knowledge-base
/dashboard/agent-tools
/dashboard/whatsapp-agent
/dashboard/payments
/dashboard/reports
/dashboard/owner-agent
```

## Documentation

```text
docs/final-implementation-roadmap.md
docs/demo-guide.md
docs/deployment-checklist.md
docs/supervisor-demo-script.md
docs/phase-21-knowledge-base.md
docs/phase-22-whatsapp-agent.md
docs/phase-23-agent-tool-layer.md
docs/phase-24-smarter-customer-ordering.md
docs/phase-25-stock-payments.md
docs/phase-26-owner-agent-reports.md
docs/phase-27-final-hardening.md
docs/phase-28-launch-wizard.md
docs/phase-29-phone-otp-onboarding.md
docs/phase-30-final-qa-demo-polish.md
docs/phase-31-submission-center.md
docs/payment-gateways.md
```

## Safety Note

Do not share real `.env` files or real API keys. Use `.env.example` for submission and demo.


## Phase 29: Phone-first OTP auth

Business owners and customers can now use phone OTP registration, phone OTP login, and phone OTP password reset. In local demo mode, the OTP is returned in the API response and defaults to `123456`. Email/password login remains available as a fallback.


## Phase 30: Final QA and Demo Polish

Open this page after seeding demo data and logging in as the business owner:

```text
/dashboard/final-qa
```

It verifies business profile, modules, catalog, RAG knowledge base, customer chatbot ordering, WhatsApp agent, stock/payments, reports, owner AI assistant, phone OTP, and demo readiness. It also contains the supervisor demo script and final verification commands.


## Phase 31: Submission Center and Evidence Pack

Open this page as the final step before FYP submission:

```text
/dashboard/submission-center
```

It maps proposal requirements to implemented phases, lists final artifacts to submit, shows files that must be excluded, records final sign-off, and exports a safe tenant evidence JSON snapshot for review.


## Phase 32: Critical Bug Fixes and Flow Stabilization

Phase 32 stabilizes the issues found during local QA: category auto-create, product image URL import, knowledge file upload UX, stronger AI product matching, follow-up order context, public/customer order confirmation fields, owner-agent product count, payment/WhatsApp/OTP clarity, and Final QA explanation. See `docs/phase-32-critical-bug-fixes.md`.


## WhatsApp Bridge

Real WhatsApp replies are delivered by a separate Node service in `whatsapp-bridge/`,
which links to WhatsApp as a companion device (the same mechanism as WhatsApp Web) and
posts inbound messages to the API. It is required for live WhatsApp; the `mock` provider
needs nothing extra.

### Setup

```bash
cd whatsapp-bridge
npm install
copy .env.example .env
npm run dev
```

Then, in the dashboard, open **WhatsApp Agent → Open WhatsApp connection page**. That
button links to this bridge's per-business pairing page
(`http://localhost:3005/pair/<tenantId>`), where the owner scans the QR from
**WhatsApp → Linked devices**. Set `WHATSAPP_BRIDGE_PUBLIC_URL` in `backend/.env` when
the bridge does not run on `localhost:3005`.

### Connecting more than one business

One bridge process serves every tenant. Each business is a separate linked device with
its own credentials.

Set `BIZXUS_BRIDGE_KEY` in `whatsapp-bridge/.env` to the same value as
`WHATSAPP_BRIDGE_ADMIN_KEY` in `backend/.env`, and the bridge asks the API which
businesses to connect: a business appears as soon as its owner saves WhatsApp settings,
with no edit to this file and no restart. An owner who clicks their pairing link before
the next refresh still gets a QR, because the bridge re-checks on a miss. The key hands
out per-tenant bridge tokens, so keep it private; leave it empty and the discovery
endpoint stays disabled.

Businesses can also be listed by hand, which still works and takes precedence:

```bash
BIZXUS_API_BASE_URL=http://127.0.0.1:8000/api/v1
BIZXUS_TENANTS=[{"tenantId":"<id>","bridgeToken":"<token>","label":"Bonanza"},{"tenantId":"<id2>","bridgeToken":"<token2>","label":"Style"}]
```

`BIZXUS_TENANTS_FILE=/path/to/tenants.json` works too, and the older single-tenant
`BIZXUS_TENANT_ID` + `BIZXUS_WHATSAPP_BRIDGE_TOKEN` pair still works unchanged.

Get each `bridgeToken` from **Dashboard → WhatsApp Agent → Refresh bridge token**.

### Health

```text
http://localhost:3005/health     per-tenant status JSON
http://localhost:3005/           QR and status page for every tenant
```

Businesses that need re-pairing also surface in the deployment readiness report under
**WhatsApp connections**.

### If WhatsApp logs the device out

Nothing to do by hand. The bridge clears the unusable credentials and shows a fresh QR
on the same pairing page. **Get a new QR code** on that page forces the same reset, and
is also how a business moves the agent to a different WhatsApp number.
