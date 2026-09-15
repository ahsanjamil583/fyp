# Phase 39: Mock OTP Payments and the Generalised Provider Protocol

Written for: developers working on this codebase, and the supervisor reviewing the demo.

Two changes, one of them architectural:

1. **A standardised payment provider protocol.** JazzCash, Easypaisa and Stripe now
   implement the same contract instead of each being wired into `payment_service` by
   hand. Adding PayFast later is a new file and one registry entry.
2. **A mock OTP wallet flow.** A wallet in `mock_otp` mode takes no redirect and moves no
   money: the customer enters a mobile number, a fresh random six-digit code is emailed
   to the address on their account, and entering it settles the order.

The mock exists so the whole payment path can be demonstrated end to end without merchant
onboarding, real money, or paid SMS. The settings validator refuses to start in production
with it enabled.

---

## The protocol

`app/integrations/payments/provider_base.py` defines one contract:

```python
class PaymentProvider(Protocol):
    code: str          # "jazzcash"
    label: str         # "JazzCash"
    flow: str          # "redirect" | "otp"

    def is_available(self) -> bool: ...
    def mode(self) -> str: ...
    def descriptor(self) -> dict: ...
    async def initiate(self, context: PaymentContext) -> InitiateResult: ...
    async def confirm(self, context: PaymentContext, proof: dict) -> ConfirmResult: ...
```

`flow` is the only thing callers branch on:

| Flow | Meaning | Providers |
|---|---|---|
| `redirect` | The customer leaves for the provider's page and the provider reports back | JazzCash, Easypaisa (simulator/sandbox/live), Stripe |
| `otp` | The customer stays here; the provider issues a challenge and settles on the right code | JazzCash, Easypaisa in `mock_otp` mode |

**Providers are stateless.** They never touch the database — signing, HTTP calls and code
generation live inside them, while `payment_service` owns what is the same for everyone:
reading the amount from the order, writing the `payment_records` row, and recomputing the
order's payment status. That split is what makes them unit-testable without Mongo.

`get_provider(code)` resolves the implementation from the configured mode, so **a request
cannot ask to be handled by the mock** — only configuration can select it.

### Adding a provider later

1. Write `app/integrations/payments/payfast.py` with its signing and callback checks.
2. Add a `PayFastProvider(BasePaymentProvider)` with `flow = "redirect"`.
3. Register it in `providers.get_provider`.

No change to `payment_service`, the routes, the web client, `payment_records`, or the
order flow.

---

## Who is offered what

Two rules, both enforced server-side:

**A guest never sees the code flow.** There is no account to email, and emailing a code to
an address an anonymous visitor typed is an abuse vector. `_wallet_method_code` downgrades
the wallet to its manual variant (`jazzcash_mock`) for guests — pay from your own wallet
app, then share the transaction ID for the owner to verify. Cash on delivery and bank
transfer are unaffected.

| Surface | `allow_otp` | JazzCash appears as |
|---|---|---|
| Customer portal (signed in) | `True` | `jazzcash`, flow `otp` |
| Public website (guest) | `False` | `jazzcash_mock`, manual |
| AI chat (serves both) | `False` | `jazzcash_mock`, manual |

**A customer without an email is blocked**, with exactly this wording, from both the
provider and the service layer:

> Please add an email to your profile to pay this way.

The dialog also checks before the customer types anything and offers a link to profile
settings, so they are not made to fill in a form that cannot succeed.

---

## The flow

```
POST /customer/transactions/{orderId}/wallet-checkout
     { provider, mobileNumber }                     -> code emailed, challenge returned

POST /customer/transactions/{orderId}/wallet-checkout/{paymentRecordId}/verify
     { code }                                       -> order marked paid

POST /customer/transactions/{orderId}/wallet-checkout/{paymentRecordId}/resend
                                                    -> new code, previous one killed
```

### What is guaranteed at each step

**Starting.** The order is loaded by `_id` **and** `customerUserId`, so one customer
cannot pay another's order. The amount is `_calculate_payment_summary(...)["balance"]` —
an OTP payment always settles the **full remaining balance**, and
`WalletOtpCheckoutRequest` has no amount field to override it with. The destination email
is read from the signed-in account, never from the request.

**The mobile number** is recorded on the payment record for the receipt and the owner's
audit trail, and is deliberately used in no decision. In a real wallet it identifies the
payer's account; here it identifies nothing, and the code says so.

**Verifying.** In order: ownership, then idempotency (an already-paid record returns
success without a second payment), then expiry, then the attempt cap, then the code
itself. The order is promoted to `paid` by `_sync_transaction_payment_status()`, the same
function every other payment path uses — nothing sets `paymentStatus` directly.

**Resending.** Every live challenge for the payment is marked `superseded` *before* the
new one is inserted, so the code in the customer's inbox is always the only one that
works.

---

## Security

| Requirement | How |
|---|---|
| No hard-coded OTP | `generate_payment_otp_code()` uses `secrets.randbelow` and **never** reads `OTP_DEMO_MODE` / `OTP_DEMO_CODE` |
| Fresh code per attempt | A new code on every start and every resend |
| Stored hashed | HMAC-SHA256 under the JWT secret, bound to the payment record id and provider |
| Never in a response | `InitiateResult.public_dict()` omits the secret; the route responses carry masked destinations only |
| Expires | 5 minutes, configurable |
| Limited attempts | 3, then the challenge locks |
| Old code invalidated | Superseded on resend |
| Amount from the database | `_calculate_payment_summary`; no amount field exists on the request |
| Constant-time comparison | `hmac.compare_digest` |

**Why this does not reuse `otp_service.py`.** Three traps, each of which would have been a
real bug:

- `generate_otp_code()` there returns `OTP_DEMO_CODE` (123456) under demo mode;
- `send_otp_email()` there **sends nothing** under demo mode, logging the code instead —
  useless to a customer sitting at a checkout;
- its challenges are keyed by a closed set of purposes with no payment purpose; widening
  it would have let anyone mint a payment-grade challenge through the public
  `/auth/otp/request` endpoint.

So the payment module reuses the *technique* and none of the code, and keeps its
challenges in a separate `payment_otp_challenges` collection. A code minted to settle a
payment can never be presented to a sign-in endpoint, or the reverse.

---

## Errors

| Case | Status | Message |
|---|---|---|
| Wrong code | 401 | `Incorrect code. 2 attempts remaining.` |
| Attempts exhausted | 423 | `Too many wrong attempts. Request a new code.` |
| Expired | 410 | `This code expired. Request a new one.` |
| No live challenge | 404 | `No active payment code was found. Start the payment again.` |
| Resend too soon | 429 | `Please wait 43 seconds before requesting another code.` |
| Resend cap reached | 429 | `Too many codes were requested for this payment. Start the payment again.` |
| Already paid | 422 | `This order is already paid.` |
| No email on profile | 422 | `Please add an email to your profile to pay this way.` |
| SMTP failure | 502 | `Could not send the payment code by email. Please try again in a moment.` |

No message says why a code was wrong beyond "wrong", and none echoes the expected value.

---

## Configuration

```bash
JAZZCASH_MODE=mock_otp
EASYPAISA_MODE=mock_otp

PAYMENT_OTP_EXPIRE_MINUTES=5
PAYMENT_OTP_MAX_ATTEMPTS=3
PAYMENT_OTP_RESEND_COOLDOWN_SECONDS=60
PAYMENT_OTP_MAX_RESENDS=3

# Real SMTP - already used by the sign-in email OTP
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=you@gmail.com
```

Modes: `simulator` (hosted fake page, the previous default), `mock_otp` (emailed code),
`sandbox`, `live`. `OTP_DEMO_MODE` can be anything — the payment path ignores it.

Set `mock_otp` with `APP_ENV=production` and the application refuses to start:

```
JAZZCASH_MODE is 'mock_otp', which settles orders on an emailed code without taking any
money. It is for local development and demos only.
```

Also switch the wallets on per business at **Dashboard → Payments** (`jazzCashEnabled`,
`easyPaisaEnabled`).

---

## Files

Backend:

```text
app/integrations/payments/provider_base.py   the contract, context and result types
app/integrations/payments/providers.py       four providers and the registry
app/integrations/payments/mock_otp.py        code generation, hashing, masking (pure)
app/services/payment_otp_service.py          challenge lifecycle: store, expire, lock, resend
tests/test_phase39_mock_otp_payments.py      46 tests
```

Modified: `app/core/config.py` (mode + OTP settings + production guard),
`app/services/payment_service.py` (provider-driven descriptors, guest gating, the three
wallet functions), `app/services/email_service.py` (`send_payment_otp_email`),
`app/schemas/payment_schema.py`, `app/api/v1/customer_portal_routes.py`,
`app/core/rate_limit.py`, `app/db/indexes.py`, `app/services/public_website_service.py`
and `app/services/ai_chat_service.py` (guest gating).

Frontend:

```text
src/features/customer/WalletOtpDialog.jsx    mobile -> code -> confirmed
src/services/paymentRedirect.js              the single redirect/OTP branch point
src/services/customerPortalApi.js            start / verify / resend
src/features/customer/CustomerOrderDetailPage.jsx
src/features/customer/CustomerCartPage.jsx
src/features/dashboard/PaymentsPage.jsx      shows the flow and the mobile number
```

---

## Demo script

1. Set `JAZZCASH_MODE=mock_otp` and real SMTP credentials in `backend/.env`, restart.
2. As the owner, **Dashboard → Payments**, enable JazzCash. Save.
3. Sign in as a customer **with an email on the account**. Add an item, checkout, choose
   JazzCash.
4. The order page opens the payment dialog. Enter any mobile number, press Pay.
5. Check the inbox: a six-digit code, the order number and the amount, with a
   "simulated payment" notice. Run it twice — the codes differ.
6. Enter a wrong code → *2 attempts remaining*. Wrong again → *1 remaining*. Again →
   locked.
7. **Send a new code.** The previous one now fails; the new one works.
8. The order flips to **paid**, and a receipt is available.
9. As the owner, **Dashboard → Payments**: the record shows JazzCash, *Verification code*,
   the mobile number, and the amount.
10. Open the public website as a guest: JazzCash appears as the manual flow, not the code
    flow.

---

## Checks

```bash
cd backend && python -m compileall app tests scripts
cd backend && python -m unittest discover -s tests -p "test_*.py" -v
cd frontend && npm run lint && npm run build
```

385 backend tests pass. An end-to-end run against a live API and MongoDB covers the happy
path, wrong codes, lockout, resend supersession, expiry, replay, cross-customer access,
guest gating, and the missing-email block.
