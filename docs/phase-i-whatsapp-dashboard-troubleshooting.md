# Phase I — WhatsApp Dashboard Polish, Timeline, and Live Meta Troubleshooting

## Goal

Phase I improves the WhatsApp Agent dashboard after Meta Embedded Signup phases E, F, G, and H. The owner now has a clearer live-readiness view, troubleshooting tools, recent Meta webhook/provider logs, and a conversation timeline for debugging real WhatsApp customer conversations.

## Added Backend APIs

- `GET /api/v1/tenants/{tenantId}/whatsapp/diagnostics`
  - Returns safe owner-facing diagnostics with masked settings, webhook URL, callback URL, verify token, readiness checklist, recent provider logs, recent routing events, and troubleshooting tips.

- `POST /api/v1/tenants/{tenantId}/whatsapp/diagnostics/test-webhook-payload`
  - Builds a Meta-shaped webhook payload using the connected tenant Phone Number ID.
  - Supports dry-run parsing/routing without sending an AI reply.
  - Can optionally process through the real AI agent flow for live troubleshooting.

- `GET /api/v1/tenants/{tenantId}/whatsapp/conversations/{conversationId}/timeline`
  - Returns a merged timeline of chat messages, WhatsApp provider logs, and routing events for one WhatsApp conversation.

## Dashboard Improvements

The WhatsApp Agent page now includes a Phase I panel with:

- Live status card.
- Webhook URL, callback URL, and verify token display.
- Readiness checklist for Meta provider, WABA ID, Phone Number ID, token, HTTPS webhook, WABA subscription, phone registration, routing, agent enabled, auto-reply enabled, recent inbound, and recent outbound.
- Recent routing events.
- Recent WhatsApp provider message logs.
- Webhook payload tester with dry-run mode and optional AI-agent processing.
- Conversation timeline viewer from the Recent WhatsApp Conversations table.

## Safety Notes

- Access tokens are never exposed to the frontend.
- Dry-run mode is the default for webhook payload testing.
- The UI warns that processing with the agent in Meta mode can send a real WhatsApp reply.
- The diagnostics API returns only safe operational status and masked settings.

## Testing

Added backend unit tests:

- Phase I checklist status helper.
- Safe default webhook test request behavior.
- Meta-shaped webhook test payload extraction.

Validation completed:

- Backend compile check passed.
- Backend unittest suite passed.
- Frontend production build passed.

## Recommended Manual Test

1. Open `/dashboard/whatsapp-agent`.
2. Confirm Phase I panel appears.
3. Check the readiness checklist.
4. Run webhook payload dry-run test.
5. Enable `Process through AI agent` only when you understand it may send a real message in Meta mode.
6. Use mock/live WhatsApp messages.
7. Open Recent WhatsApp Conversations.
8. Click `View timeline` and verify chat messages, provider logs, and routing events appear.
