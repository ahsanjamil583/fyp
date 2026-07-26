# BizXusAI Deployment Checklist

Use this checklist before final FYP demo, supervisor review, or deployment.

## 1. Repository Cleanup

```text
Do not include backend/.env with real secrets
Do not include frontend/node_modules
Do not include backend/__pycache__
Do not include logs
Do not include uploads with private files
Do not include chroma-data runtime folder unless intentionally sharing demo vectors
Keep .env.example only
```

## 2. Backend Setup

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
```

Update `.env`:

```text
APP_ENV=development for local demo
DEBUG=true for local demo
JWT_SECRET_KEY=use-a-long-random-secret
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=bizxus_ai
WHATSAPP_PROVIDER=mock for FYP demo
SMS_PROVIDER=mock for FYP demo
RATE_LIMIT_ENABLED=false for local demo, true for public deployment
```

## 3. Frontend Setup

```bash
cd frontend
npm install
npm run build
npm run dev
```

Update `frontend/.env` if needed:

```text
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## 4. Database and Demo Data

Start MongoDB, then:

```bash
cd backend
python scripts/seed_demo_data.py
```

Demo accounts:

```text
Business Owner: owner@bizxus.demo / Demo@12345
Customer: customer@bizxus.demo / Demo@12345
Admin: admin@bizxus.demo / Admin@12345
Public Website: /businesses/demo-bazaar
```

## 5. Run Application

Backend:

```bash
cd backend
python -m uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm run dev
```

## 6. Run Checks

Backend compile:

```bash
cd backend
python -m compileall app tests scripts
```

Backend unit tests:

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py" -v
```

Frontend build:

```bash
cd frontend
npm run build
```

Smoke check:

```bash
cd backend
python scripts/smoke_check.py http://localhost:8000/api/v1
```

## 7. Dashboard Readiness Page

Open:

```text
/dashboard/deployment-readiness
```

Confirm:

```text
No failed checks
Warnings are acceptable for local/demo mode
Version shows 0.27.0
Build label shows phase-27-final-hardening
Demo account info is visible
```

## 8. Core Demo Flow

```text
1. Login as business owner
2. Open Deployment Readiness
3. Open Business profile
4. Show public website
5. Show items with variants
6. Open Knowledge Base and show owner-uploaded knowledge
7. Open customer/public chatbot and ask for a black hoodie/size
8. Confirm draft order
9. Show stock/payment/transaction updates
10. Show WhatsApp Agent mock simulator
11. Show Owner AI Assistant
12. Show Reports and deliver-now dry run
```

## 9. Production Safety

For real deployment:

```text
APP_ENV=production
DEBUG=false
JWT_SECRET_KEY must be changed
CORS_ORIGINS must use your frontend domain only
Use HTTPS
Use gateway/server-level rate limiting
Use real WhatsApp/SMS credentials only if required
Use secure backup strategy for MongoDB
Do not expose demo credentials publicly
```
