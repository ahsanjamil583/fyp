# Phase J — WhatsApp Go-Live Acceptance Test and Final Runbook

## Goal

Phase J closes the Meta WhatsApp Embedded Signup implementation with a final owner-facing go-live checklist, a manual acceptance-test runbook, and a sign-off record. It is used after:

- Phase E: WABA webhook subscription
- Phase F: Phone number registration
- Phase G: webhook routing by Phone Number ID
- Phase H: live AI/RAG/catalog/order replies
- Phase I: dashboard troubleshooting and timeline tools

## Backend APIs

- `GET /api/v1/tenants/{tenantId}/whatsapp/go-live/checklist`
  - Returns the Phase J readiness checklist, counts, latest go-live run, and final test runbook.

- `POST /api/v1/tenants/{tenantId}/whatsapp/go-live/test-run`
  - Records a manual real/mock WhatsApp acceptance test result.
  - Stores customer phone/name, test message, verified steps, notes, and result.

## Dashboard UI

The WhatsApp Agent page now includes a Phase J panel with:

- Overall status: `needs_setup`, `ready_for_demo`, or `ready_for_live`.
- Required failures and warnings.
- Checklist cards covering Meta provider, WABA ID, Phone Number ID, token, HTTPS webhook, WABA subscription, phone registration, routing, agent/auto reply, inbound/outbound logs, WhatsApp transactions, handoff, and manual sign-off.
- Final runbook for real customer testing.
- Recent counts for WhatsApp conversations, orders, inbound logs, outbound replies, and failures.
- Manual test-run form to record the final QA/supervisor result.

## Manual Test Flow

1. Message the connected business WhatsApp number from a customer phone.
2. Ask: `Zinger burger available hai?`
3. Confirm the AI replies from the correct business catalog/RAG.
4. Ask: `2 zinger burgers order kar do`.
5. Provide delivery/pickup, address/city, and confirmation.
6. Verify the order appears in Transactions and stock is reserved.
7. Send a handoff phrase such as `human se baat karni hai`.
8. Verify the owner receives a handoff notification.
9. Open conversation timeline and verify inbound message, AI reply, provider logs, and routing events.
10. Record the Phase J test run.

## Safety

- No Meta token is exposed in the frontend.
- Phase J does not send messages by itself; it records acceptance results and reads operational logs.
- The owner can use mock mode for FYP demo or real Meta mode for production testing.
