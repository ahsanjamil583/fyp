# Development Guide

## Implementation Flow

Implement phases in dependency order:

1. Phase 0: planning and standards
2. Phase 1: runnable backend/frontend base
3. Phase 2: authentication and identity access
4. Phase 4: tenants, categories, modules
5. Phase 6: custom fields
6. Phase 7: customers
7. Phase 8: items/services
8. Phase 11: public website and minimal orders
9. Phase 12: customer marketplace
10. Phase 13: analytics
11. Phase 14: AI chat with RAG
12. Phase 15: testing, hardening, deployment

Follow the generalized roadmap lock in [Final Locked Implementation Roadmap](final-implementation-roadmap.md) when deciding what belongs in each phase.

## Product Direction

Build BizxusAI as a generalized platform for any business category.

Important rule:

- restaurant, pharmacy, and retail are demo categories only
- categories must configure behavior, not fork backend logic

## Backend Conventions

- Keep routes thin.
- Put business logic in services.
- Put shared auth, permissions, tenant checks, and module checks in `core`.
- Use Pydantic schemas for request and response validation.
- Use Motor for async MongoDB access.
- Create database indexes explicitly in `db/indexes.py`.
- Keep tenant filters close to the database query.
- Recalculate prices on the backend.

## Frontend Conventions

- Use React Router for route groups.
- Use TanStack Query for server state.
- Use Context API for auth, customer, tenant, and module state.
- Use React Hook Form and Joi for forms.
- Use Axios through `services/apiClient.js`.
- Keep feature-specific pages under `features`.
- Keep reusable UI under `components`.

## Frontend Routes

Public routes:

- `/`
- `/login`
- `/register`
- `/businesses/:tenantSlug`
- `/businesses/:tenantSlug/items`
- `/businesses/:tenantSlug/chat`

Customer portal routes:

- `/customer/register`
- `/customer/login`
- `/customer/marketplace`
- `/customer/businesses/:tenantSlug`
- `/customer/businesses/:tenantSlug/items`
- `/customer/businesses/:tenantSlug/chat`
- `/customer/cart`
- `/customer/orders`
- `/customer/orders/:orderId`
- `/customer/profile`
- `/customer/notifications`

Business dashboard routes:

- `/dashboard`
- `/dashboard/business`
- `/dashboard/modules`
- `/dashboard/custom-fields`
- `/dashboard/customers`
- `/dashboard/items`
- `/dashboard/items/import`
- `/dashboard/public-website`
- `/dashboard/analytics`
- `/dashboard/ai-conversations`
- `/dashboard/payments`
- `/dashboard/reports`
- `/dashboard/notifications`

Admin routes:

- `/admin`
- `/admin/users`
- `/admin/tenants`
- `/admin/business-categories`
- `/admin/modules`
- `/admin/reports`
- `/admin/notifications`

## Context API State Plan

`AuthContext` owns:

- business owner/admin auth token
- authenticated user profile
- login/logout helpers
- business-dashboard access state

`CustomerContext` owns:

- customer auth token
- customer profile
- customer login/logout helpers
- customer portal access state

`TenantContext` owns:

- selected tenant
- available owner tenants
- tenant switching
- tenant refresh helpers

`ModuleContext` owns:

- enabled modules for selected tenant
- module guard helper state
- dynamic sidebar/module visibility

## Layout Groups

The frontend will have four route worlds:

- public website routes
- customer portal routes
- business dashboard routes
- admin routes

Each group should have its own layout and guard strategy.

The visual direction is a clean professional SaaS dashboard style.

## Testing Expectations

Minimum tests should cover:

- auth flows
- tenant ownership
- customer isolation
- module guards
- custom field validation
- backend price calculation
- public visibility rules
- AI order confirmation rule

## Demo Data

The MVP should eventually include:

- Burger Restaurant
- Retail Store
- Clinic as a future-proof category

Appointments are intentionally skipped for the clinic demo.

These are example tenants for demonstration only. The implementation itself must remain category-agnostic and reusable for any business type.
