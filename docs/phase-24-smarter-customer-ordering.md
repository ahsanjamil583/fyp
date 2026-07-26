# Phase 24 — Smarter Customer Ordering

## Goal

Phase 24 makes the customer-side AI ordering flow production-ready for the FYP demo. Customers can ask for products or services naturally, including color, size, material, quantity, budget, and delivery intent. The agent prepares a safer draft order and the backend revalidates it before creating the transaction.

## What was implemented

### 1. Smart order validation service

Added:

```text
backend/app/services/smart_order_service.py
```

This service centralizes order-line resolution for customer portal orders and public website orders.

It handles:

```text
item lookup by tenant
variant resolution by selectedVariantIndex
variant resolution by variantSku
variant resolution by selectedOptions
fallback to default/single variant
backend price recalculation
stock availability validation
transaction line building
```

### 2. Variant-aware confirmation

Customer AI drafts already contained variant details from Phase 23. Phase 24 now preserves those values during confirmation:

```text
selectedVariantIndex
selectedVariantName
selectedOptions
variantSku
```

The backend does not trust frontend prices. It reloads the live item and selected variant, recalculates price, and stores variant details in the final transaction.

### 3. Stock-checked draft orders

The agent draft now includes a stock snapshot on every line:

```text
tracked
scope
available
availableQuantity
requestedQuantity
message
```

The draft also includes:

```text
canConfirm
confirmationIssues
pricing
requestedAttributes
budget
fulfillmentPreference
```

If stock is insufficient, the customer sees the issue and the confirm button is disabled. The backend also blocks confirmation if stock is no longer available.

### 4. Better customer intent extraction

The agent now understands more practical ordering signals:

```text
color
size
material
quantity
budget / under price
bring / send / delivery intent
pickup intent
Roman Urdu order terms
```

Example messages:

```text
2 black shirts deliver kar do
red medium hoodie chahiye
burger under 500 order kar do
black shoes size 42 chahiye
```

### 5. Multi-item draft support

If the customer clearly mentions multiple exact item names using connectors like `and`, `aur`, comma, or `+`, the agent can create multiple draft lines.

Example:

```text
2 burgers aur 1 fries order kar do
```

### 6. Customer portal UI upgraded

Updated:

```text
frontend/src/features/customer/CustomerBusinessChatPage.jsx
```

The customer chat page now shows:

```text
variant name
selected options
editable quantity
unit price
line total
stock availability
confirmation issues
requested attributes
fulfillment preference
estimated total
suggested matches with matched variants
```

The confirm request now sends selected variant/options to the backend.

### 7. Public AI chat guest confirmation

Updated:

```text
frontend/src/features/public/PublicBusinessChatPage.jsx
backend/app/schemas/public_website_schema.py
backend/app/services/public_website_service.py
```

Public visitors can now confirm an AI-generated draft from the public website chat by entering:

```text
name
phone / WhatsApp number
optional email
delivery address when delivery is detected
```

This creates a public website transaction and notifies the business owner.

### 8. Customer and public transaction creation now use the same smart order logic

Updated:

```text
backend/app/services/customer_portal_service.py
backend/app/services/public_website_service.py
```

Both flows now use the same backend validation service, so AI chat confirmation and normal public orders follow the same safer pricing/variant/stock rules.

## Acceptance checklist

- [x] Customer chatbot understands color/size/material terms.
- [x] Customer chatbot detects budget hints.
- [x] Customer chatbot detects delivery/pickup intent.
- [x] Draft orders include selected variant details.
- [x] Draft orders include stock snapshots.
- [x] Draft orders include confirmation readiness.
- [x] Customer portal confirms draft with variant/options.
- [x] Backend recalculates price from live item data.
- [x] Backend validates item/variant/stock before transaction creation.
- [x] Public website chat supports guest draft confirmation.
- [x] Business owner receives notification when public/customer AI order is confirmed.
- [x] Backend Python compile check passes.
- [x] Frontend production build passes.

## Notes for Phase 25

Phase 24 validates stock but does not yet deduct or reserve stock. Phase 25 should implement:

```text
stock reservation for pending orders
stock deduction after confirmed order
restore stock on cancel/reject
variant-level stock deduction
payment status + COD/manual payment completion
```
