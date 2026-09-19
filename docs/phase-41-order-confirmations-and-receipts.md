# Phase 41: Order Confirmations and Online Order Receipts

Written for: developers working on this codebase, and the supervisor reviewing the demo.

Two things a customer expects after ordering online and did not previously get:

1. **A confirmation message** — on email, and on WhatsApp when the business has a paired
   number. Sent when the order is placed, and again when payment is confirmed.
2. **A receipt for the whole order** — a printable page at a link that works without
   logging in, so it can be put straight into the confirmation message.

Neither is allowed to break an order. Every send is wrapped: a dead SMTP server, an
unpaired WhatsApp number or a missing email address is recorded and skipped, and the order
still goes through.

---

## What already existed, and what is new

There were already two receipt artefacts, and both are untouched:

| Artefact | Covers | Where |
|---|---|---|
| Payment receipt | one payment record | `GET /customer/payments/{id}/receipt` |
| Cashier slip | one counter sale | `cashier_order_service` thermal layout |
| **Order receipt** (new) | **the whole order** | `GET /receipts/{token}` |

An order can have several payments, so the payment receipt could never stand in for the
order. The new one is the document a customer would call "my receipt".

---

## The receipt

`app/services/order_receipt_service.py` renders server-side HTML. There is no PDF: adding
a PDF library for one page is not worth the dependency, and every browser prints HTML.

**Addressing.** Each transaction gets a `receiptToken` — 32 random URL-safe characters,
minted on first use by `ensure_receipt_token()`. The route takes the token, never the
transaction id:

```
GET /api/v1/receipts/{receiptToken}     # no auth, 404 on an unknown token
```

The reason is that transaction ids are MongoDB ObjectIds, which are partly a timestamp and
a counter and are therefore guessable. A token is not. `ensure_receipt_token()` backfills
races safely: two concurrent calls both attempt a conditional update and the loser re-reads
the winner's token instead of overwriting it.

**Contents.** Business name and contact, order number, date, line items with quantities and
line totals, subtotal, discount, tax, total, amount paid, balance, and the payment status
in words. Costs, margins, stock levels and internal ids are not on it. All interpolated
values go through `receipt_text()` in `app/core/receipt_format.py`, which escapes — an item
named `<img onerror=...>` renders as text.

**Getting the link.** A signed-in customer can ask for their own order's token:

```
GET /api/v1/customer/transactions/{orderId}/receipt-link   ->  { "receiptToken": "..." }
```

The order detail page has a **View receipt** button that opens it in a new tab.

---

## The messages

`app/services/order_message_service.py`. Two events:

| Event | Fires when |
|---|---|
| `order_placed` | a customer order is created |
| `payment_confirmed` | a payment settles the order (`paymentStatus` becomes `paid`) |

Payment confirmation is hooked into `_sync_transaction_payment_status`, so it fires for
every provider — Stripe redirect, wallet OTP, or a manual mark-as-paid — without any of
them knowing about it. It only fires on an actual transition, so a second settlement call
on an already-paid order sends nothing. Cash on delivery never reaches `paid` at checkout,
so it produces one message, not two.

**Channels.** Email uses the address on the order. WhatsApp is attempted only when
`whatsapp_is_reachable()` says the tenant's number is paired — the WhatsApp provider always
succeeds at writing its own log row, so pairing status is the only honest test of whether a
message will actually arrive.

**Sources that stay silent.** `cashier` and `imported`. A counter customer is standing at
the till and already has the printed slip; an imported historical order must not email
someone about a sale from three months ago.

**Sent once.** `order_message_deliveries` has a unique index on
`(transactionId, event, channel)`. The row is inserted *before* the send, not after — a
claim, not a log. Writing it afterwards would leave a window in which a replayed gateway
callback sends a second copy while the first is still in flight, which is the failure the
index exists to prevent. A `DuplicateKeyError` means someone else already has the claim, so
this caller stops.

---

## Owner controls

Per-tenant, in `order_message_settings`, defaults all on — a business that never opens the
panel still confirms its orders.

```
GET  /api/v1/tenants/{tenantId}/order-messages
PUT  /api/v1/tenants/{tenantId}/order-messages
```

| Field | Effect |
|---|---|
| `emailEnabled` | send on email at all |
| `whatsappEnabled` | send on WhatsApp at all |
| `sendOnOrderPlaced` | confirm when the order is placed |
| `sendOnPaymentConfirmed` | confirm when payment lands |
| `footerNote` | up to 300 characters appended to both channels |

The read also returns `emailConfigured`, so the UI can say that SMTP is not set up rather
than letting the owner wonder why nothing arrives.

The controls live at the bottom of **Notifications** in the owner dashboard, and stay
reachable when the notifications module is switched off — order confirmations are not part
of that module.

Owner-facing email and WhatsApp are deliberately out of scope. Owners already get in-app
business alerts on the same page.

---

## Templates

English only. Email is sent as plain text plus HTML; WhatsApp is short plain text, since a
long message in a chat window is worse than a link. Both carry the order number, total,
payment status and the receipt link.

---

## Verification

- 40 unit tests in `backend/tests/test_phase41_order_messages.py`; the full suite is 559.
- 26 end-to-end checks against a live API and MongoDB with SMTP stubbed, covering: one
  email per placed order, correct addressee and total, no cost-price leak, token minted,
  receipt opens with no login, unknown token 404s, exactly one delivery row, payment
  confirmation is a distinct message, a second settlement does not resend, the receipt
  reads "Paid", guest orders are confirmed, an order with no email is still accepted,
  WhatsApp is skipped for an unpaired business, settings default on, switching email off
  stops emails, and an SMTP failure does not fail the order.
