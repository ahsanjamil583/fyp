# Phase 25 — Stock Reservation, Deduction, and Payment Completion

## Status

Implemented.

## Objective

Phase 25 completes the operational reliability layer for AI/customer orders. After this phase, an order is no longer just a transaction record; it also affects inventory and can be connected with COD/manual/local wallet payment records.

## Implemented Backend Capabilities

### 1. Stock Reservation

When a customer, public visitor, or AI draft confirmation creates an order:

1. Live item data is reloaded from MongoDB.
2. Variant and selected options are revalidated.
3. Stock availability is checked again.
4. Stock is reserved immediately for tracked products.
5. The transaction receives an inventory state.

Inventory states:

```text
reserved
not_required
released
deducted
```

### 2. Variant-Level Reservation

For items with variants, the system now supports:

```text
variants.{index}.reservedQuantity
variants.{index}.stockQuantity
```

This means orders for specific colors/sizes do not only depend on the parent item quantity.

### 3. Stock Deduction

When an order status changes to:

```text
completed
```

The system deducts the reserved stock from live inventory.

For normal stock items:

```text
stock.quantity decreases
stock.reservedQuantity decreases
```

For variant stock items:

```text
variant.stockQuantity decreases
variant.reservedQuantity decreases
```

### 4. Stock Release

When an order status changes to:

```text
cancelled
```

Reserved stock is released back into availability.

### 5. Inventory Movement Logs

Every inventory action creates a movement record:

```text
reserve
release
deduct
```

Collection:

```text
inventory_movements
```

These records are linked to:

```text
tenantId
transactionId
transactionNumber
itemId
variantIndex
quantity
movementType
```

### 6. Low Stock Notifications

After stock deduction, the system checks item and variant thresholds. If stock is at or below the threshold, a business notification is created.

### 7. Payment Settings

Business owners can configure payment settings from:

```text
/dashboard/payments
```

Supported methods:

```text
COD
Manual verification
JazzCash-ready settings
EasyPaisa-ready settings
Bank transfer/manual settings
```

### 8. Payment Recording

Owners can record payment against outstanding orders:

```text
completed
pending
failed
```

Completed payments update the transaction payment status automatically:

```text
unpaid
partially_paid
paid
refunded
```

### 9. Refund Recording

Owners can record refunds. Refunds update the transaction payment summary and create payment history.

## New Backend Files

```text
backend/app/services/inventory_service.py
backend/app/services/payment_service.py
backend/app/schemas/payment_schema.py
backend/app/api/v1/payment_routes.py
```

## Updated Backend Files

```text
backend/app/services/customer_portal_service.py
backend/app/services/public_website_service.py
backend/app/services/smart_order_service.py
backend/app/services/transaction_service.py
backend/app/api/v1/router.py
backend/app/db/indexes.py
```

## New Frontend Files

```text
frontend/src/features/dashboard/PaymentsPage.jsx
frontend/src/services/paymentApi.js
```

## Updated Frontend Files

```text
frontend/src/app/router.jsx
frontend/src/features/dashboard/TransactionsPage.jsx
```

## New Backend APIs

```text
GET  /api/v1/tenants/{tenantId}/payments/settings
PUT  /api/v1/tenants/{tenantId}/payments/settings
GET  /api/v1/tenants/{tenantId}/payments/overview
POST /api/v1/tenants/{tenantId}/payments/transactions/{transactionId}/record
POST /api/v1/tenants/{tenantId}/payments/transactions/{transactionId}/refund
```

## Testing Flow

1. Enable these modules:

```text
customer_portal
items
payments
notifications
```

2. Create an item with tracked stock.
3. Create an order through customer portal, public website, or AI chat.
4. Check that the transaction inventory status becomes `reserved`.
5. Change order status to `completed`.
6. Check that stock is deducted.
7. Create another order and cancel it.
8. Check that reserved stock is released.
9. Open `/dashboard/payments`.
10. Configure payment methods.
11. Record COD/manual payment.
12. Confirm transaction payment status changes to `paid` or `partially_paid`.

## Notes

- The JazzCash and EasyPaisa parts are gateway-ready/mock-friendly for FYP. The owner can store numbers and record verified local wallet payments manually.
- Real payment gateway callbacks can be added later by extending `payment_service.py` and adding provider integration files.
