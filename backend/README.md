# BizXusAI Backend

FastAPI backend for BizXusAI.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload
```

## Main Health Endpoints

```text
GET /api/v1/health
GET /api/v1/health/readiness
GET /api/v1/health/demo-accounts
GET /api/v1/health/phase-summary
```

## Demo Data

```bash
python scripts/seed_demo_data.py
```

Creates:

```text
owner@bizxus.demo / Demo@12345
customer@bizxus.demo / Demo@12345
admin@bizxus.demo / Admin@12345
/businesses/demo-bazaar
```

## Tests and Checks

```bash
python -m compileall app tests scripts
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/smoke_check.py http://localhost:8000/api/v1
```

## Backup

```bash
python scripts/backup_mongo.py
```

## Production Notes

```text
APP_ENV=production
DEBUG=false
JWT_SECRET_KEY must be strong
CORS_ORIGINS must be restricted
RATE_LIMIT_ENABLED=true or use gateway-level rate limiting
Use HTTPS and secure MongoDB credentials
```

## WhatsApp Embedded Signup - Phase A Preparation

Phase A prepares the Meta Developer App and environment values. It does not connect a tenant yet.

Add these values to `backend/.env` after creating/configuring the Meta app:

```text
META_APP_ID=your_meta_app_id_here
META_APP_SECRET=your_meta_app_secret_here
META_EMBEDDED_SIGNUP_CONFIG_ID=your_embedded_signup_configuration_id_here
META_GRAPH_API_VERSION=v21.0
META_BUSINESS_LOGIN_REDIRECT_PATH=/dashboard/whatsapp-agent/connect/callback
BACKEND_PUBLIC_URL=https://your-ngrok-or-deployed-backend.example.com
FRONTEND_BASE_URL=http://localhost:5173
WHATSAPP_VERIFY_TOKEN=bizxus-whatsapp-verify
```

Configure these URLs in Meta Developer Dashboard:

```text
Frontend callback:
{FRONTEND_BASE_URL}{META_BUSINESS_LOGIN_REDIRECT_PATH}

Backend webhook:
{BACKEND_PUBLIC_URL}/api/v1/webhooks/whatsapp
```

Local development needs a public HTTPS tunnel such as ngrok for `BACKEND_PUBLIC_URL`; Meta webhooks cannot call `localhost`.

Use `/dashboard/whatsapp-agent` to view the Phase A readiness checklist after restarting the backend.

## WhatsApp Embedded Signup - Phase C Capture

Phase C stores the browser result from Meta Embedded Signup for the selected tenant. It does not exchange tokens yet.

Dashboard flow:

1. Open `/dashboard/whatsapp-agent`.
2. Click `Connect with Meta`.
3. Complete the Meta popup flow.
4. Click `Save signup response`.

Backend endpoint:

```text
POST /api/v1/tenants/{tenantId}/whatsapp/embedded-signup/capture
```

The endpoint stores the Meta authorization code, WABA ID, Phone Number ID, business WhatsApp number, and Meta Business ID when Meta provides them. The tenant connection status becomes `pending_token_exchange`, which is the handoff point for the next phase.

Saved authorization codes are not returned raw from settings APIs. The dashboard only receives masked/status fields.

## WhatsApp Embedded Signup - Phase D Token Exchange

Phase D exchanges the saved Meta authorization code for a business access token. The token is stored only in the backend database and is never returned to the frontend.

Dashboard flow:

1. Complete Phase C first so the business status is `pending_token_exchange`.
2. Open `/dashboard/whatsapp-agent`.
3. Click `Exchange token`.
4. If Meta accepts the code, the connection status becomes `token_exchanged`.

Backend endpoint:

```text
POST /api/v1/tenants/{tenantId}/whatsapp/embedded-signup/exchange-token
```

Required environment values:

```text
META_APP_ID=your_meta_app_id_here
META_APP_SECRET=your_meta_app_secret_here
META_GRAPH_API_VERSION=v21.0
FRONTEND_BASE_URL=http://localhost:5173
META_BUSINESS_LOGIN_REDIRECT_PATH=/dashboard/whatsapp-agent/connect/callback
```

After a successful exchange, Phase E should subscribe the connected WABA to webhooks, and Phase F should register the phone number if Meta requires it.


## Phase 28 Launch APIs

```text
GET  /api/v1/tenants/{tenantId}/launch/status
POST /api/v1/tenants/{tenantId}/launch/apply-profile
POST /api/v1/tenants/{tenantId}/launch/finalize
```


## Phase 29: Phone-first OTP auth

Business owners and customers can now use phone OTP registration, phone OTP login, and phone OTP password reset. In local demo mode, the OTP is returned in the API response and defaults to `123456`. Email/password login remains available as a fallback.


## Phase 30: Final QA APIs

```text
GET  /api/v1/tenants/{tenantId}/qa/checklist
POST /api/v1/tenants/{tenantId}/qa/demo-run
GET  /api/v1/health/phase-summary
```

Use `/dashboard/final-qa` in the frontend for the final supervisor demo checklist and manual QA run recording.


## Phase 31: Submission Center APIs

```text
GET  /api/v1/tenants/{tenantId}/submission/package
GET  /api/v1/tenants/{tenantId}/submission/export
POST /api/v1/tenants/{tenantId}/submission/signoff
GET  /api/v1/health/submission-summary
```

Use `/dashboard/submission-center` in the frontend to review proposal traceability, record final sign-off, and export a safe tenant evidence snapshot.

## Meta WhatsApp Embedded Signup - Phase E webhook subscription

After Phase D exchanges the Embedded Signup authorization code for a business token, open the WhatsApp Agent dashboard and click **Subscribe webhooks**.

Required `.env` values:

```env
BACKEND_PUBLIC_URL=https://your-ngrok-or-deployed-backend.example.com
WHATSAPP_VERIFY_TOKEN=bizxus-whatsapp-verify
META_GRAPH_API_VERSION=v21.0
```

The backend endpoint used by the dashboard is:

```text
POST /api/v1/tenants/{tenantId}/whatsapp/embedded-signup/subscribe-webhooks
```

The endpoint subscribes the connected WABA to this app's webhook and saves:

```text
webhookSubscriptionStatus=subscribed
webhookCallbackUrl={BACKEND_PUBLIC_URL}/api/v1/webhooks/whatsapp
webhookSubscribedAt=<timestamp>
```

For local testing, use ngrok so Meta can reach your webhook URL. `localhost` cannot be used as a Meta webhook callback.

### Phase F: Register WhatsApp phone number

After Phase E webhook subscription, open the WhatsApp Agent page and enter a 6-digit registration PIN. The backend will register the connected Phone Number ID with Meta Cloud API using the stored business token. The PIN is not saved in BizXusAI.

### Phase H: Live WhatsApp AI replies

After Meta Embedded Signup phases A-G are complete, Phase H lets routed WhatsApp messages use the BizXusAI AI/RAG/catalog/order agent. The same webhook endpoint receives a customer message, resolves the tenant by Meta Phone Number ID, creates or loads a WhatsApp conversation, runs the agent, and sends a short WhatsApp-safe reply. If a draft order is pending, WhatsApp follow-up messages such as `delivery`, `House 12, Attock`, and `confirm` update or confirm the draft order and create a transaction.

Recommended mock test sequence from the WhatsApp Agent dashboard:

1. `2 zinger burgers order kar do`
2. `delivery`
3. `House 12, Main Road, Attock`
4. `confirm`

A successful confirmation should create a WhatsApp transaction, reserve stock, clear the pending draft, and notify the business owner.
