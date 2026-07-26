# Phase 8 — Payment Receipts and Checkout Proof

Phase 8 adds printable payment receipts for the payment flow implemented in the Stripe/local payments rollout.

## What It Adds

- Owner receipt endpoint for tenant payment records
- Customer receipt endpoint for customer order payment records
- Shared receipt HTML generator with business, customer, transaction, item, and payment details
- Authenticated frontend receipt fetch helpers
- Owner dashboard receipt button in the payment records table
- Customer portal receipt button in order payment history
- Print/save-as-PDF support through the browser print dialog

## Backend Routes

```text
GET /api/v1/tenants/{tenantId}/payments/records/{paymentRecordId}/receipt
GET /api/v1/customer/transactions/{orderId}/payments/{paymentRecordId}/receipt
```

Both routes return HTML and reuse existing access rules:

- Business owners can only access receipt records for their tenant.
- Customers can only access receipts for their own transactions.

## Frontend Screens

- `/dashboard/payments`
- `/customer/orders/{orderId}`

## Supported Payment Records

- COD
- Manual bank transfer
- JazzCash mock
- EasyPaisa mock
- Stripe test card
- Refund records

## Testing

Validated with:

```text
python -m unittest discover -s tests -p "test_phase25_stock_payments.py"
python -m unittest discover -s tests -p "test_customer_portal_service.py"
npm run build
```

