# Phase 28 — Launch Wizard and One-Click Setup

## Objective

Phase 28 closes the remaining onboarding gap from the proposal: a non-technical business owner should move from setup to an AI-ready published business website through a guided launch flow.

## Implemented capabilities

- Launch Wizard dashboard page at `/dashboard/launch-wizard`.
- Backend launch readiness API.
- One-click launch profiles:
  - `basic_website`
  - `ai_ordering`
  - `full_agent_demo`
- Automatic module enabling with dependency support through the existing module system.
- Optional mock plan upgrade so FYP/demo profiles can enable Growth/Scale modules without real billing friction.
- Safe default bootstrapping for website settings, COD/manual payment settings, report delivery settings, and mock WhatsApp connection rows.
- Readiness checklist for:
  - business profile
  - recommended modules
  - catalog/service items
  - website builder
  - AI + RAG knowledge
  - customer ordering
  - WhatsApp agent
  - daily reports
- Finalize action that attempts to publish the website and records Phase 28 completion metadata.
- Final QA now recognizes `settings.onboarding.phase28.finalizedAt` as launch evidence.
- New backend tests for launch profile normalization and launch summary behavior.

## Backend files added

```text
backend/app/api/v1/onboarding_routes.py
backend/app/services/onboarding_service.py
backend/app/schemas/onboarding_schema.py
backend/tests/test_phase28_onboarding.py
```

## Frontend files added

```text
frontend/src/features/dashboard/LaunchWizardPage.jsx
frontend/src/services/onboardingApi.js
```

## Updated files

```text
backend/app/api/v1/router.py
backend/app/core/config.py
frontend/src/app/router.jsx
frontend/src/components/layout/DashboardLayout.jsx
docs/final-implementation-roadmap.md
```

## New APIs

```text
GET  /api/v1/tenants/{tenantId}/launch/status
POST /api/v1/tenants/{tenantId}/launch/apply-profile
POST /api/v1/tenants/{tenantId}/launch/finalize
```

## Recommended demo flow

1. Log in as the business owner.
2. Open `/dashboard/business` and complete the business profile.
3. Open `/dashboard/launch-wizard`.
4. Apply `AI Ordering Launch` or `Full Agent Demo Launch`.
5. Review the auto-prepared website/payment/report/WhatsApp defaults.
6. Add/import at least one active item.
7. Add at least one knowledge base document.
8. Click `Finalize & Publish`.
9. Open the public website and test customer AI ordering.

## Status

Phase 28 is implemented and ready for testing.
