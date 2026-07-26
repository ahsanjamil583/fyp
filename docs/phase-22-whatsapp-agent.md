# Phase 22 — WhatsApp Agent Integration

Phase 22 connects a business owner's WhatsApp number to the same BizXus AI assistant pipeline used by website chat and customer portal chat.

## Implemented scope

- Owner dashboard page: `/dashboard/whatsapp-agent`
- New module registry entry: `whatsapp_agent`
- Owner can save WhatsApp connection settings
- Mock/FYP provider support
- Meta WhatsApp Cloud API-ready provider branch
- Tenant-specific webhook verify token
- Public webhook verification endpoint
- Public webhook receive endpoint
- Mock inbound WhatsApp simulator
- Test outbound message sender
- WhatsApp conversation persistence with `channel: "whatsapp"`
- AI auto-replies using existing RAG + catalog + draft-order planner
- Handoff keywords for routing a conversation to owner review
- Recent WhatsApp conversation list in dashboard
- Delivery/inbound logs in `whatsapp_message_logs`

## Main backend files

```text
backend/app/api/v1/whatsapp_routes.py
backend/app/services/whatsapp_service.py
backend/app/schemas/whatsapp_schema.py
backend/app/integrations/whatsapp/provider.py
backend/app/core/config.py
backend/app/db/indexes.py
backend/app/db/seeders/seed_modules.py
```

## Main frontend files

```text
frontend/src/features/dashboard/WhatsAppAgentPage.jsx
frontend/src/services/whatsappApi.js
frontend/src/app/router.jsx
frontend/src/components/layout/DashboardLayout.jsx
```

## Owner flow

1. Owner enables `AI Chat` and `WhatsApp Agent` modules.
2. Owner opens `/dashboard/whatsapp-agent`.
3. Owner enters WhatsApp number and selects provider.
4. For FYP/demo, owner uses `mock` provider.
5. The page shows webhook URL and verify token.
6. Owner can simulate customer WhatsApp messages.
7. AI replies using RAG, catalog data, and draft order planning.

## Customer WhatsApp flow

1. Customer sends a WhatsApp message to the connected business number.
2. Webhook receives the message.
3. System maps the message to the correct tenant/business.
4. A `channel: "whatsapp"` conversation is created or reused.
5. Customer message is saved.
6. BizXus AI generates a reply using the existing AI pipeline.
7. Reply is sent through the configured WhatsApp provider.
8. Owner can review the conversation from AI Chat and WhatsApp Agent screens.

## API endpoints

```text
GET    /api/v1/webhooks/whatsapp
POST   /api/v1/webhooks/whatsapp
GET    /api/v1/tenants/{tenantId}/whatsapp/settings
PUT    /api/v1/tenants/{tenantId}/whatsapp/settings
POST   /api/v1/tenants/{tenantId}/whatsapp/disconnect
GET    /api/v1/tenants/{tenantId}/whatsapp/conversations
POST   /api/v1/tenants/{tenantId}/whatsapp/mock/inbound
POST   /api/v1/tenants/{tenantId}/whatsapp/send-test
```

## Environment variables

```env
WHATSAPP_PROVIDER=mock
WHATSAPP_VERIFY_TOKEN=bizxus-whatsapp-verify
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_API_VERSION=v21.0
```

## Notes

- Mock mode is best for FYP because it requires no paid Meta setup.
- Real Meta Cloud API can be used by setting provider to `meta_cloud`, adding `phoneNumberId`, and saving an access token.
- Final order confirmation is still handled by the existing draft/order flow. Full WhatsApp order confirmation with customer address collection should be improved in the later customer-ordering/stock/payment phases.
