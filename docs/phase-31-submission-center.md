# Phase 31 — Submission Center and Evidence Pack

## Objective

Phase 31 adds a final submission/evidence layer for the BizXusAI FYP package. It helps the business owner or developer verify that the implemented code matches the proposal, record a final sign-off, and export a safe tenant evidence snapshot before submission.

## Delivered Capabilities

- Submission Center dashboard page at `/dashboard/submission-center`
- Proposal-to-code traceability table
- Final artifact checklist
- Clean submit/exclude file lists
- Tenant evidence counts for items, RAG documents, WhatsApp conversations, payments, reports, QA runs, and submission sign-offs
- Final sign-off recording
- Safe tenant evidence JSON export
- Recursive secret/token/password redaction in exported evidence
- Required-artifact validation before `ready` / `ready_with_notes` sign-off
- Public submission summary endpoint for smoke testing
- Updated smoke check script
- Updated phase summary to Phase 31

## Backend APIs

```text
GET  /api/v1/tenants/{tenantId}/submission/package
GET  /api/v1/tenants/{tenantId}/submission/export
POST /api/v1/tenants/{tenantId}/submission/signoff
GET  /api/v1/health/submission-summary
```

## Frontend Route

```text
/dashboard/submission-center
```

## Main Files Added

```text
backend/app/api/v1/submission_routes.py
backend/app/services/submission_service.py
backend/app/schemas/submission_schema.py
frontend/src/features/dashboard/SubmissionCenterPage.jsx
frontend/src/services/submissionApi.js
backend/tests/test_phase31_submission.py
docs/phase-31-submission-center.md
```

## Final Submission Rule

Submit only the latest cleaned project zip. Do not submit runtime/generated files such as:

```text
.env
node_modules/
__pycache__/
logs/
uploads/
chroma-data/
test-results/
```

Use `.env.example` instead of `.env`.

## Sign-Off Rule

Final sign-off can only be marked `ready` or `ready_with_notes` when all required artifacts are selected:

```text
latest_zip
proposal_pdf
demo_guide
env_example
seed_demo_data
```

If any required artifact is missing, use `blocked` or complete the artifact checklist first.
