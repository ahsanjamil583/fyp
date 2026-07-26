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
