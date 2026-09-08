> **Superseded.** This phase documented the Meta WhatsApp Cloud API integration, which
> was replaced by the Baileys linked-device bridge in `whatsapp-bridge/`. The webhook
> routes described here no longer exist and the provider now accepts only `mock` or
> `baileys`. Kept for project history; see the "WhatsApp Bridge" section of `README.md`
> for the current setup.

# Phase F — Meta WhatsApp Phone Number Registration

Phase F registers the verified WhatsApp Business phone number for Cloud API use after Embedded Signup token exchange and WABA webhook subscription.

## Flow

1. Business owner completes Embedded Signup.
2. Backend exchanges signup code for business token.
3. Backend subscribes the customer WABA to webhooks.
4. Owner enters a 6-digit registration PIN in the WhatsApp Agent page.
5. Backend calls Meta `/{phone-number-id}/register` with `messaging_product=whatsapp` and the PIN.
6. Backend stores `phoneRegistrationStatus=registered` and never stores the PIN.

## New API

`POST /api/v1/tenants/{tenantId}/whatsapp/embedded-signup/register-phone`

Body:

```json
{
  "pin": "123456"
}
```

## Notes

- The PIN is sent once to Meta and is not stored by BizXusAI.
- WABA webhooks must be subscribed before phone registration.
- The business token must already be stored from Phase D.
- This is required for real WhatsApp Cloud API auto-replies.
