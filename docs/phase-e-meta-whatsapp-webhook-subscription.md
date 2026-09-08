> **Superseded.** This phase documented the Meta WhatsApp Cloud API integration, which
> was replaced by the Baileys linked-device bridge in `whatsapp-bridge/`. The webhook
> routes described here no longer exist and the provider now accepts only `mock` or
> `baileys`. Kept for project history; see the "WhatsApp Bridge" section of `README.md`
> for the current setup.

# Phase E - Meta WhatsApp WABA Webhook Subscription

Phase E completes the next step after Embedded Signup token exchange. After the business owner finishes Meta Embedded Signup and the backend exchanges the returned code for a business token, BizXusAI must subscribe the connected WhatsApp Business Account (WABA) to this app's webhook.

## What this phase adds

- Backend service for subscribing a tenant WABA to Meta WhatsApp webhooks.
- Backend endpoint:
  - `POST /api/v1/tenants/{tenantId}/whatsapp/embedded-signup/subscribe-webhooks`
- Dashboard button in WhatsApp Agent page:
  - **Subscribe webhooks**
- Subscription status tracking on each WhatsApp integration:
  - `webhookSubscriptionStatus`
  - `webhookSubscriptionAttemptedAt`
  - `webhookSubscribedAt`
  - `webhookCallbackUrl`
  - `webhookProviderResponse`
  - `lastError`
- Clear UI status for Phase E and the next step, Phase F phone number registration.

## Required prerequisites

Before clicking **Subscribe webhooks**, the business must have:

1. Completed Phase C signup capture.
2. Completed Phase D token exchange.
3. Saved WABA ID / WhatsApp Business Account ID.
4. Saved business access token from Meta.
5. `BACKEND_PUBLIC_URL` set to a public HTTPS URL, such as ngrok or deployed backend.
6. A webhook verify token.

## Local testing with ngrok

Start backend:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Expose it:

```bash
ngrok http 8000
```

Set:

```env
BACKEND_PUBLIC_URL=https://your-ngrok-url.ngrok-free.app
WHATSAPP_VERIFY_TOKEN=bizxus-whatsapp-verify
```

Restart backend, then go to:

```text
/dashboard/whatsapp-agent
```

Click **Subscribe webhooks** after Phase D token exchange is complete.

## What happens internally

The backend calls Meta Graph API:

```text
POST /{WABA_ID}/subscribed_apps
```

with the business access token. If callback override is supported for the current Meta app configuration, the backend also sends:

```text
override_callback_uri = {BACKEND_PUBLIC_URL}/api/v1/webhooks/whatsapp
verify_token = tenant/global verify token
```

If Meta rejects callback override fields, the backend falls back to a plain WABA subscription request using only the access token.

## Next phase

After Phase E succeeds, implement Phase F:

- Register the connected phone number for WhatsApp Cloud API use.
- Verify send/receive using the tenant Phone Number ID.
