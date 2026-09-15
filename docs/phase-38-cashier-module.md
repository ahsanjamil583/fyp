# Phase 38: Cashier Module and Order Sheet Import

Written for: developers working on this codebase, and the supervisor reviewing the demo.

This phase adds counter (point-of-sale) operation to every business on the platform, and a
way to bring a business's pre-BizXusAI sales history into the same order model.

Two capabilities, one module:

1. **Cashiers.** A business owner registers staff logins. A cashier signs in at the normal
   business login page, lands on a separate till screen, records in-store orders, and
   prints receipts. They never see the owner dashboard, the admin area, or another
   business's data.
2. **Order sheet import.** The owner uploads an old Excel or CSV sales sheet. It is parsed,
   shown back for review, and only written once the owner confirms.

Nothing about the existing owner, customer, marketplace, public-website, payment or AI
flows changes. Cashier and imported orders are ordinary rows in `transactions`, so the
owner's order queue, analytics, reports, inventory and customer history pick them up with
no per-source special casing.

---

## Turning it on

The module is `cashier`, seeded alongside the others and depending on `items`.

- New businesses get every module enabled, so it is on already.
- An existing business enables it at **Dashboard → Modules**, or from the button on
  **Dashboard → Cashiers** when the module is off.

Server-side, every cashier route calls `ensure_tenant_module_enabled(tenant, "cashier")`,
so disabling the module actually stops the feature rather than only hiding its menu entry.

---

## Roles

| | Business owner | Cashier |
|---|---|---|
| Account type | `business_owner` | `cashier` |
| Signs in at | `/login` | `/login` (same form) |
| Lands on | `/dashboard` | `/cashier` |
| Manages cashiers | yes | no |
| Sees all business orders | yes | only cashier orders, and only their own unless granted |
| Creates counter orders | — | yes |
| Imports order sheets | yes | no |
| Business profile, modules, website, AI, payments, admin | yes | **no** |

A cashier account is two documents:

- a row in `users` with `accountType: "cashier"` and a `tenantId`, so the existing JWT,
  session-version and password machinery works unchanged;
- a row in `cashiers` holding the tenant-scoped profile, permissions and running totals.

The `tenantId` lives on the account, not in the request. That is what makes cross-tenant
access impossible rather than merely discouraged: no cashier endpoint accepts a tenant id.

### Per-cashier permissions

| Permission | Default | Effect when off |
|---|---|---|
| `canViewAllCashierOrders` | off | The cashier sees only the orders they created. |
| `canAddCustomItems` | on | Manual, non-catalog lines are refused. |
| `canApplyDiscount` | on | Any non-zero discount is refused. |

---

## Cashier screens

```text
/cashier                       Today's sales, today's orders, pending/unpaid, completed, recent orders
/cashier/orders/new            The till: search catalog, tap to add, charges, payment, confirm
/cashier/orders                Order list with search and status filter
/cashier/receipts              The same list, framed as reprints
/cashier/receipts/:token       The printable receipt
```

The layout is deliberately not the owner shell: four destinations, large tap targets, no
business switcher, no plan badge, nothing that can be clicked by mistake with a queue
waiting.

### Order entry

Customer name, phone and optional email; catalog items with variants; manual lines for
anything not in the catalog; discount and tax as either a flat amount or a percentage;
service charge and delivery fee; order type (in-store, dine-in, takeaway, pickup,
delivery); payment method (cash, card, JazzCash, Easypaisa, bank transfer, or
unpaid/pending); amount received with change due; and notes.

Totals are computed in the browser for instant feedback and **recomputed on the server**
before saving. The figure printed on a receipt is always the server's.

Pricing order, which the tests pin:

```text
subtotal  = Σ (unit price × quantity)
discount  = flat amount, or percent of subtotal
tax       = flat amount, or percent of (subtotal − discount)
total     = subtotal − discount + tax + service charge + delivery fee
```

### Inventory

| Situation | What happens to stock |
|---|---|
| Paid counter sale | Deducted. The goods left the shop. |
| Unpaid / held order | Reserved, exactly as a customer order would be. |
| Manual (non-catalog) line | Nothing. There is no catalog row to move. |
| Not enough stock | The order is refused with a message naming the item and what is left; the till screen warns before that, from the quantities in the catalog panel. |

Counter sales go through the same `inventory_service` transitions as every other order,
so reservations, movements, low-stock notifications and reconciliation all behave the same.

### Receipts

A receipt carries the business name, logo, address and phone; the receipt number, date and
cashier; the customer when one was given; item lines with quantity and unit price; the
discount, tax and charges; the total; the payment method; a paid/pending stamp; and a
footer message.

It is addressed by an unguessable `receiptToken`, never by the transaction's ObjectId, and
the cashier projection drops cost prices, stock snapshots, internal notes, status history
and every internal id. **Print Receipt** hides the navigation and chrome (`print-hide`) and
sizes the sheet for 80mm thermal paper, falling back cleanly to A4.

---

## Order sheet import

```text
/dashboard/orders/import
```

Upload, review, then commit. **The upload step writes nothing.** It returns what the parser
understood, which rows it could not read, and which look like orders already in the
business's records. A mis-mapped column therefore costs a second upload, not a corrupted
order history.

### Columns

One row per item. Repeat the same order number across rows and they become one order with
several lines. Every column is optional as long as a row has either an item or an amount.

`Order number`, `Order date`, `Customer name`, `Customer phone`, `Customer email`,
`Item name`, `SKU`, `Quantity`, `Unit price`, `Discount`, `Tax`, `Total amount`,
`Payment method`, `Payment status`, `Order status`, `Notes`.

Header spelling is flexible — `Order No`, `Invoice Number` and `orderNumber` all reach the
same field, and the review screen lists both what was matched and what was ignored rather
than guessing.

### What the parser tolerates

- Dates as `2025-03-18`, `18/03/2025`, `18-Mar-2025`, `2025-03-18 14:30` and similar. A date
  it cannot read fails **that row only**, and says so.
- Amounts written as `Rs 1,500.50` or `PKR 3,001.00`.
- A line total with no unit rate: the rate is derived from total ÷ quantity.
- Status words: `Delivered`, `Completed`, `Cancelled`, `Paid`, `Due`, `Cash on Delivery`
  and so on map onto the platform's own vocabulary.
- A stated total that disagrees with the line arithmetic is **flagged, not silently
  changed** — the sheet is the record of what was actually charged.

Files: `.xlsx`, `.xlsm` and `.csv`, up to 8 MB and 5000 data rows. The legacy binary `.xls`
format is not readable by `openpyxl`; the error says so and asks for a re-save, which is a
ten-second fix in Excel.

### Imported orders

- `source: "imported"`, so the owner can filter for them.
- The original order number and date are preserved. A number that collides with one the
  business already issued gets a suffix rather than failing the import.
- **Stock is not moved.** Those goods left the shelf whenever the original sale happened,
  often months ago; replaying it now would corrupt today's inventory. Rows are marked
  `inventoryStatus: "not_required"`.
- Customers with a phone or email join the normal customer list and stats.

### Duplicate protection

An order matches an existing one by order number when it has one, and otherwise by
date + customer name + phone + amount (normalized, so `+92 300 1234567` and `03001234567`
are the same customer). Re-uploading the same sheet reports the rows as already present and
skips them.

### Import history

Every run records the file name, who ran it, when, and the row counts — total, imported,
skipped and failed. Runs with problems offer a downloadable CSV report naming each row and
what happened to it.

---

## The unified order model

Everything lands in `transactions`, distinguished by `source`:

```text
customer_portal   marketplace / customer portal
website           public business website
ai_chat           AI assistant and WhatsApp drafts
cashier           in-store counter sale
imported          historical sheet import
```

The owner filters by source at **Dashboard → Orders**, and the Cashiers and Import pages
deep-link into that filter. Analytics, reports, inventory and customer history read the
collection without filtering by source, so the new rows are included automatically.

---

## API

Owner, under the existing tenant guard:

```text
GET    /tenants/{tenantId}/cashiers
POST   /tenants/{tenantId}/cashiers
GET    /tenants/{tenantId}/cashiers/{cashierId}
PUT    /tenants/{tenantId}/cashiers/{cashierId}
POST   /tenants/{tenantId}/cashiers/{cashierId}/status
POST   /tenants/{tenantId}/cashiers/{cashierId}/password
DELETE /tenants/{tenantId}/cashiers/{cashierId}

GET    /tenants/{tenantId}/transactions/imports/columns
POST   /tenants/{tenantId}/transactions/imports/preview
POST   /tenants/{tenantId}/transactions/imports/confirm
GET    /tenants/{tenantId}/transactions/imports
GET    /tenants/{tenantId}/transactions/imports/{importId}/errors.csv
```

Cashier, under the cashier guard. None takes a tenant id:

```text
GET    /cashier/me
GET    /cashier/dashboard
GET    /cashier/catalog
GET    /cashier/orders
POST   /cashier/orders
GET    /cashier/orders/{receiptToken}
GET    /cashier/receipts/{receiptToken}
```

`POST /auth/login` now accepts both `business_owner` and `cashier` and reports which signed
in. `GET /auth/me` does the same. Every other owner and admin route still depends on
`get_current_business_user`, which refuses a cashier token with 403.

---

## Security

- Passwords are bcrypt-hashed through the same `hash_password` and checked against the same
  strength policy as owner passwords.
- Deactivating a cashier suspends the login **and** bumps `sessionVersion`, so a token
  already in their browser stops working on the next request rather than at expiry. The
  same happens on a password reset and on removing access.
- Removing access withdraws the login but keeps the profile, so historical receipts keep a
  cashier name.
- The tenant boundary is enforced by the account, not the request, and every owner route
  still goes through `get_owned_tenant_or_403`.
- Receipts are addressed by token; no cashier or receipt response carries a database id, a
  cost price, a stock level, internal notes or workflow state.
- Import file type, size and row count are capped, every row is validated, and duplicates
  are checked against the database at confirm time, not only at preview.

---

## Files

Backend:

```text
app/schemas/cashier_schema.py            request contracts for all three audiences
app/services/cashier_service.py          owner-side cashier CRUD, cashier context resolution
app/services/cashier_order_service.py    till dashboard, order entry, listing, receipts
app/services/order_import_service.py     sheet parsing, preview, confirm, history, report
app/api/v1/cashier_routes.py             owner_router + cashier_router
app/api/v1/order_import_routes.py        owner import endpoints
tests/test_phase38_cashier_module.py     47 tests
```

Frontend:

```text
src/components/layout/CashierLayout.jsx        the till shell
src/features/cashier/CashierDashboard.jsx
src/features/cashier/CashierNewOrderPage.jsx
src/features/cashier/CashierOrdersPage.jsx
src/features/cashier/CashierReceiptPage.jsx
src/features/cashier/cashierShared.jsx         shared formatting
src/features/cashiers/CashiersPage.jsx         owner-side management
src/features/dashboard/OrderImportPage.jsx     owner-side import
src/services/cashierApi.js
src/services/orderImportApi.js
```

Touched: `app/core/security.py` (cashier dependency), `app/services/auth_service.py` and
`app/api/v1/auth_routes.py` (shared login), `app/services/inventory_service.py` (skip
non-catalog lines), `app/services/customer_service.py` (accurate source tags),
`app/db/seeders/seed_modules.py`, `app/db/indexes.py`, `app/api/v1/router.py`,
`src/app/router.jsx`, `src/components/layout/DashboardLayout.jsx`,
`src/components/common/ProtectedRoute.jsx`, `src/context/AuthContext.jsx`,
`src/features/auth/BusinessLogin.jsx`, `src/features/auth/ForcedPasswordResetPage.jsx`,
`src/features/dashboard/TransactionsPage.jsx`, `src/styles.css`, `src/utils/moduleMeta.js`.

---

## Demo script

1. Sign in as the owner. Open **Dashboard → Cashiers**, enable the module if prompted.
2. **Add cashier** — name, email, temporary password. Note the sign-in line in the
   confirmation.
3. Sign out. Sign in at the same `/login` with the cashier's credentials → you land on
   `/cashier`, not the dashboard.
4. Try `/dashboard` or `/admin` in the address bar → bounced back to `/cashier`.
5. **New order** — search the catalog, tap two items, add a manual line, set a 10% discount,
   choose Cash, confirm.
6. The receipt opens. **Print Receipt** — the preview shows the receipt alone.
7. Sign back in as the owner. **Dashboard → Orders**, filter source `cashier` → the sale is
   there with the cashier's name. Check **Catalog & Stock**: the tracked item went down.
8. **Dashboard → Import Orders** — upload an old CSV, review the parsed orders and the
   flagged rows, confirm. Filter orders by source `imported`.
9. Upload the same file again → every row is reported as already present.

---

## Checks

```bash
cd backend && python -m compileall app tests scripts
cd backend && python -m unittest discover -s tests -p "test_*.py" -v
cd frontend && npm run lint && npm run build
```
