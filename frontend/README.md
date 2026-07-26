# BizXusAI Frontend

React + Vite + Tailwind frontend for BizXusAI.

## Setup

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
npm run preview
```

## Environment

Create `.env` if the backend is not on the default local URL:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

## Important Demo Routes

```text
/login
/customer/login
/businesses/demo-bazaar
/businesses/demo-bazaar/chat
/customer/businesses/demo-bazaar/chat
/dashboard/deployment-readiness
/dashboard/knowledge-base
/dashboard/whatsapp-agent
/dashboard/owner-agent
```


## Phase 28 Launch Wizard

Open `/dashboard/launch-wizard` after selecting a tenant to apply a one-click launch profile, review readiness, and publish the business website.


## Phase 29: Phone-first OTP auth

Business owners and customers can now use phone OTP registration, phone OTP login, and phone OTP password reset. In local demo mode, the OTP is returned in the API response and defaults to `123456`. Email/password login remains available as a fallback.


## Phase 30: Final QA Dashboard

```text
/dashboard/final-qa
```

This page shows the final full-system QA score, blocking gaps, warnings, supervisor demo script, verification commands, and a manual demo-run recorder.
