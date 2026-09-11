# Payment gateways: Stripe, JazzCash, Easypaisa

Three online methods take the customer to a payment page and bring them back with a
signed result. Cash on delivery and manual bank transfer stay as they were: settled by
the owner rather than by a gateway.

## The flow

```text
Cart
  └─ customer picks a payment method
Checkout  POST /customer/transactions
  └─ the order (transaction) is created first, so the payment has something to reference
     ├─ offline method (COD / bank)  → order page, owner settles it later
     └─ online method                → POST /customer/transactions/{orderId}/gateway-checkout
Gateway
  ├─ a payment_record is written with status "pending_verification"
  ├─ the order moves to paymentStatus "pending_verification"
  └─ the customer is redirected:
       stripe     GET  Stripe Checkout
       jazzcash   POST signed form → JazzCash
       easypaisa  GET  Easypay
Customer pays (or cancels)
  └─ the gateway returns them to  /payments/{provider}/callback
       ├─ the signature is verified first; an unsigned or altered callback is never a payment
       ├─ paid      → payment_record "paid", order recalculated → "paid"
       └─ cancelled → payment_record "failed", order recalculated → "rejected"
Order page  /customer/orders/{orderId}
       stripe    ?payment=stripe_success&session_id=...  (the page re-checks Stripe)
       wallets   ?payment=success | cancelled | failed   (already settled server-side)
Dashboard → Transactions / Payments
  └─ shows method, amount, currency, gateway reference, provider, mode, status
```

The order is created before payment on purpose: the payment record, receipt, refund, and
the owner's Transactions view all key off a real transaction. The customer still
experiences one continuous flow, because checkout redirects immediately.

### What a completed payment records

| Field | Example |
|---|---|
| `method` / `methodLabel` | `jazzcash` / `JazzCash` |
| `amount`, `currency` | `4200.0`, `PKR` |
| `status` | `paid` |
| `referenceNumber`, `providerTransactionId` | the gateway's transaction id |
| `provider`, `providerMode` | `jazzcash`, `sandbox` |
| `providerResponseCode` | `000` |
| `transactionId`, `transactionNumber` | the order it belongs to |

Replaying a callback for an already-paid record is a no-op, so a gateway retry cannot
double-pay an order.

### Route layout

| Endpoint | Auth |
|---|---|
| `POST /customer/transactions/{orderId}/gateway-checkout` | customer |
| `POST /customer/transactions/{orderId}/stripe-checkout` | customer |
| `GET\|POST /payments/{provider}/callback` | public (signature-verified) |
| `GET\|POST /payments/{provider}/simulator/{ref}` | public, simulator mode only |

Starting a checkout must stay under `/customer/`: the web client chooses the customer
access token by that path prefix and sends the business token to anything else, so a
customer-only endpoint outside it is called with the wrong token and answers 403.

## Modes

`JAZZCASH_MODE` and `EASYPAISA_MODE` each take `simulator`, `sandbox`, or `live`.

- **simulator** — a payment page served by this API at
  `/api/v1/payments/{provider}/simulator/{ref}` with **Pay** and **Cancel** buttons. It
  exists because JazzCash and Easypaisa credentials require merchant onboarding, so the
  flow would otherwise be untestable until that completes. Its callbacks are signed with
  the same code the real gateways use, so the signature check is exercised locally.
- **sandbox** — the gateway's own test environment.
- **live** — production.

`sandbox` and `live` fall back to `simulator` when credentials are missing, rather than
sending a customer to a gateway that will reject the request. In production the simulator
is never offered to customers: the method falls back to the manual owner-verified flow,
and a `live` mode with missing credentials refuses to boot.

## Setting up each gateway

### Stripe — available immediately

1. Create an account at <https://dashboard.stripe.com/register>.
2. With **Test mode** on, copy the keys from Developers → API keys.
3. In `backend/.env`:
   ```bash
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```
4. For webhooks locally: `stripe listen --forward-to localhost:8000/api/v1/payments/stripe/webhook`
   and copy the `whsec_...` it prints.
5. Dashboard → Payments → enable Stripe. The API refuses to enable it without a secret
   key, and the checkout hides Stripe when no key is set, so set the key first.

Stripe test mode accepts PKR, so no currency change is needed. `charges_enabled: false`
on an unactivated test account is normal and does not block test payments.

Without `stripe listen` running there is no webhook, and the order page falls back to
re-checking the session when the customer returns. Payment still records; the webhook
matters for customers who close the tab before returning.

Test cards (any future expiry, any CVC, any postcode):

| Card | Result |
|---|---|
| `4242 4242 4242 4242` | succeeds |
| `4000 0000 0000 0002` | declined |
| `4000 0025 0000 3155` | requires 3-D Secure |
| `4000 0000 0000 9995` | insufficient funds |

### JazzCash — needs merchant onboarding

There is no self-service sandbox signup. Apply through
<https://sandbox.jazzcash.com.pk/> or a JazzCash business representative; you will need
business registration details. They issue **Merchant ID**, **Password**, and **Integrity
Salt** for sandbox, and separate values for production.

```bash
JAZZCASH_MODE=sandbox
JAZZCASH_MERCHANT_ID=MC12345
JAZZCASH_PASSWORD=your_password
JAZZCASH_INTEGRITY_SALT=your_integrity_salt
```

Sandbox test wallet numbers and OTPs come with the credentials pack; JazzCash normally
supplies a test mobile number that accepts OTP `123456`. Until then use
`JAZZCASH_MODE=simulator`.

The integration is the documented HTTP POST page-redirection flow: fields are sorted,
empty values dropped, joined with `&` behind the integrity salt, and signed with
HMAC-SHA256. Amounts go to JazzCash in **paisa** (PKR 4200 → `420000`).

### Easypaisa — needs merchant onboarding

Apply through Telenor Microfinance Bank / Easypaisa merchant services. They issue a
**Store ID** and a **hash key**. The hash key must be exactly 16 characters, because
Easypay uses it as an AES-128 key.

```bash
EASYPAISA_MODE=sandbox
EASYPAISA_STORE_ID=12345
EASYPAISA_HASH_KEY=SixteenCharKey12
```

Sandbox testing uses the test MSISDN and OTP supplied with the credentials. Until then
use `EASYPAISA_MODE=simulator`.

The integration is the Easypay redirect: the signed parameter string is AES-128-ECB
encrypted under the hash key and base64 encoded as `merchantHashedReq`.

## Testing today, without gateway credentials

1. `backend/.env` — leave `JAZZCASH_MODE=simulator` and `EASYPAISA_MODE=simulator`.
2. Dashboard → Payments → enable JazzCash and Easypaisa (and Stripe if you have keys).
3. As a customer: add an item, open the cart, pick JazzCash or Easypaisa, press Checkout.
   (Stripe only appears once `STRIPE_SECRET_KEY` is set; it is hidden rather than shown
   as a button that could only fail.)
4. The simulated gateway page opens. Press **Pay** or **Cancel**.
5. You land back on the order page; the order shows paid or rejected.
6. Dashboard → Transactions and Payments show the record with its reference and provider.

Automated coverage lives in `backend/tests/test_payment_gateways.py`: signing, tamper
detection for both gateways, unsigned callbacks, mode fallback, and the legacy method
migration.

## Going live

1. Replace the sandbox credentials with production ones.
2. Set both modes to `live`.
3. Set `BACKEND_PUBLIC_URL` to a public HTTPS address. The gateways call
   `/payments/{provider}/callback` on it, so localhost will not work.
4. Set `APP_ENV=production`. Boot then fails if a gateway is `live` without credentials,
   and customers can no longer be routed to the simulator.
5. Confirm one real low-value payment per gateway before announcing it.
