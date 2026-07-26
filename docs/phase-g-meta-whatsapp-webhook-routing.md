# Phase G — Meta WhatsApp Webhook Routing by Phone Number ID

Phase G completes the multi-business WhatsApp routing layer for Meta Embedded Signup.

## Purpose

Every business connected through Meta Embedded Signup has its own WhatsApp Phone Number ID. Meta sends incoming WhatsApp webhook payloads to one BizXusAI backend URL. BizXusAI must route each incoming message to the correct tenant by reading:

```text
entry[].changes[].value.metadata.phone_number_id
```

## Implemented behavior

- Incoming Meta webhook messages are flattened into routing events.
- `metadata.phone_number_id` is the primary routing key.
- Display phone number is used only as a fallback for older/manual setups.
- If the Phone Number ID maps to a connected tenant, BizXusAI loads that tenant and sends the message to the existing WhatsApp AI agent pipeline.
- The AI reply is sent using that same tenant's Meta Phone Number ID and access token.
- Duplicate inbound provider message IDs are still ignored by the existing message-log logic.
- Delivery/read/failed status webhook events are parsed and applied to matching outbound message logs.
- Unmatched or unsupported webhook events are recorded without crashing the entire webhook request.
- Routing status is exposed in the dashboard.
- A Phase G routing test can verify that the connected Phone Number ID resolves to the selected business.

## New backend APIs

```text
GET  /api/v1/tenants/{tenantId}/whatsapp/embedded-signup/routing-status
POST /api/v1/tenants/{tenantId}/whatsapp/embedded-signup/test-routing
```

## Updated webhook endpoint

```text
POST /api/v1/webhooks/whatsapp
```

The endpoint now returns a structured summary:

```json
{
  "processedCount": 1,
  "skippedCount": 0,
  "errorCount": 0,
  "statusCount": 0,
  "items": [],
  "skipped": [],
  "errors": [],
  "statuses": []
}
```

## Dashboard changes

The WhatsApp Agent page now shows **Phase G: Webhook routing by Phone Number ID** after Phase F phone registration.

It displays:

- routing readiness
- Phone Number ID
- webhook callback URL
- last webhook received time
- missing routing prerequisites
- routing test form

## Data stored

`whatsapp_integrations` now updates:

- `webhookRoutingStatus`
- `lastWebhookReceivedAt`
- `lastWebhookPhoneNumberId`
- `lastRoutingTestAt`

A new collection is used for debug/audit events:

```text
whatsapp_routing_events
```

## Validation

- Backend compile check passed.
- Backend unittest suite passed.
- Frontend production build passed.

## Next phase

Phase H should connect the routed WhatsApp webhook fully to the business AI/RAG/catalog/order agent experience and polish live WhatsApp response handling.
