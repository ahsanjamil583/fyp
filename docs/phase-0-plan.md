# Phase 0 Plan

## Objective

Prepare BizxusAI for phased implementation by documenting architecture, coding standards, environment variables, tenant isolation rules, storage abstraction, AI/RAG boundaries, frontend application structure, and the generalized product direction.

Phase 0 does not implement runtime backend/frontend features. It creates the technical foundation for Phase 1.

## Locked Product Direction

BizxusAI is a generalized multi-tenant AI-powered business automation platform for Pakistani SMEs.

The original proposal used restaurant, pharmacy, and retail as example categories. The implementation direction is now generalized so the platform can support any business category through configuration.

Locked rules:

- business categories are configuration, not backend control flow
- restaurant, pharmacy, and retail remain seeded demo categories only
- modules define capability exposure per tenant
- custom fields define category and tenant flexibility
- tenant-aware AI and RAG remain part of the core architecture

## Selected Scope

The implementation will include only the selected phases from the blueprint plus the generalized roadmap lock-in:

- Phase 0
- Phase 1
- Phase 2
- Phase 4
- Phase 7
- Phase 8
- Phase 9
- Phase 11
- Phase 12
- Phase 13
- Phase 14
- Phase 15
- Phase 16
- Phase 20
- Phase 22
- Phase 23

The core FYP MVP target is Phase 0 through Phase 15. Phases 16, 20, 22, and 23 are post-MVP enhancements unless timeline allows.

See the finalized roadmap in [Final Locked Implementation Roadmap](final-implementation-roadmap.md).

## Skipped Phase Rules

Some skipped phases still require minimum dependency logic:

- Full tenant management is skipped, but minimal tenant creation is required.
- Full RBAC is skipped, but role checks are required.
- Branch management is skipped, so tenant-owned records include `branchId: null`.
- Full transaction management is skipped, but minimal order transactions are required.
- Workflow builder is skipped, so simple fixed statuses are used.
- Advanced AI agents are skipped, so use basic AI chat and rule-based fallback.
- Subscription billing is skipped, so paid-plan enforcement is not added.

## Phase 0 Deliverables

- Root README
- Architecture decisions
- API response and error standards
- Environment variable plan
- Security and tenant isolation rules
- Development guide
- Final locked implementation roadmap
- Backend `.env.example`
- Frontend `.env.example`

## Phase 1 Entry Criteria

Before starting Phase 1, confirm:

- Backend stack remains FastAPI, Python, Pydantic, MongoDB, JWT, bcrypt.
- Frontend stack remains React, JavaScript, Vite, Tailwind, React Router, TanStack Query, Context API, React Hook Form, Joi, Axios.
- MongoDB Atlas will be used for main data.
- ChromaDB will be introduced with a placeholder client in Phase 1.
- Business categories remain configuration only.
- The platform direction remains generalized for any business category.

## User-Confirmed Decisions

- Project name: `BizxusAI`
- Backend MongoDB driver: Motor
- Development database: local MongoDB
- Deployment database: MongoDB Atlas
- Primary image storage provider: ImageKit
- Frontend location: repository `frontend/` folder
- UI direction: clean professional SaaS dashboard style
- Backend deployment target: Railway
- Frontend deployment target: Vercel
- Groq API: configured through local/deployment secrets only, never committed
- Original proposal categories remain demo examples, not hardcoded product boundaries
