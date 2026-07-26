# Security and Tenant Isolation

## Account Types

Supported account types:

- `business_owner`
- `customer`

Supported global roles:

- `platform_admin`
- `user`

## Access Rules

Business owners:

- can access only tenants where `ownerUserId` equals the authenticated user ID
- cannot access customer-only APIs unless explicitly allowed
- cannot access admin APIs

Customers:

- can access customer portal APIs
- can view published businesses
- can access only their own cart, orders, profile, conversations, and notifications
- cannot access business dashboard APIs

Platform admins:

- can access admin APIs
- can manage categories, modules, users, tenants, and admin reports

Public users:

- can view only published and visible businesses
- can create public website orders where allowed
- cannot access private tenant dashboard data

## Tenant-Owned Record Rules

Every tenant-owned record must include:

- `tenantId`
- `branchId: null` for now

Tenant isolation must be enforced in service queries, not only in frontend route guards.

## Module Guard Rules

Module-protected routes must check:

- tenant ownership or admin access
- module exists
- module is enabled for the tenant
- module is active globally

If a module is disabled, return `MODULE_DISABLED`.

## Order Security

Customer and public order requests must not include trusted prices.

Allowed client input:

- item ID
- quantity
- fulfillment choice
- address/contact info
- notes

Backend-owned calculation:

- item name snapshot
- unit price
- subtotal
- discount
- tax
- delivery fee
- total

## AI Safety Rules

AI-assisted ordering must follow:

- AI can suggest an order draft.
- AI cannot create a final order directly.
- Customer confirmation is required.
- RAG retrieval must be tenant-isolated.
- Prompt injection attempts must not override tenant isolation, price calculation, or confirmation rules.

## File Upload Rules

Uploads must validate:

- file type
- file size
- tenant/user ownership

Excel imports must use temporary storage and delete files after parsing.

## Notification Isolation

Notifications must be scoped by:

- `tenantId` for business notifications
- `customerUserId` for customer notifications

Cross-tenant notification access is forbidden.
