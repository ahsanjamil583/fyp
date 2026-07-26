# BizXusAI Final Demo Guide

This guide explains the recommended demo flow for the final FYP/project presentation.

## Demo Goal

Show that BizXusAI is no longer just a website builder. It is a generalized AI-powered business automation platform where any business owner can manage products/services, upload knowledge, connect WhatsApp, let AI answer customer queries, create smart orders, handle stock/payments, and receive insights.

## Demo Preparation

```bash
cd backend
python scripts/seed_demo_data.py
python -m uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Demo Accounts

```text
Business owner: owner@bizxus.demo / Demo@12345
Customer: customer@bizxus.demo / Demo@12345
Admin: admin@bizxus.demo / Admin@12345
Public website: /businesses/demo-bazaar
```

## Recommended Demo Sequence

### 1. Deployment Readiness

Open:

```text
/dashboard/deployment-readiness
```

Explain:

```text
This page verifies MongoDB, Chroma/RAG, upload directories, integration settings, security headers, rate limit config, and runtime version.
```

### 2. Business Dashboard

Show:

```text
Business profile
Enabled modules
Generalized category/module system
```

Explain:

```text
The system is generalized. Restaurant, pharmacy, retail, clothing, and services can be handled through configuration, modules, custom fields, and catalog data.
```

### 3. Catalog and Variants

Open:

```text
/dashboard/items
```

Show:

```text
Premium Hoodie with black/red variants
Classic Black Shoes with size variants
Zinger Burger as food item
```

Explain:

```text
The AI agent can search by name, color, size, budget, stock, and custom fields.
```

### 4. Knowledge Base / RAG

Open:

```text
/dashboard/knowledge-base
```

Show:

```text
Delivery and payment policy
Size and color guide
```

Explain:

```text
The business owner can upload knowledge. The AI uses this knowledge to answer customer queries accurately.
```

### 5. Customer/Public Chat Ordering

Open:

```text
/businesses/demo-bazaar/chat
```

Try:

```text
black hoodie large chahiye delivery ke sath
black shoes size 42 order kar do
burger under 600 chahiye
```

Explain:

```text
The AI extracts intent, searches catalog, matches variants, checks stock, prepares draft order, and asks for confirmation.
```

### 6. Customer Portal

Login as customer and open:

```text
/customer/businesses/demo-bazaar/chat
```

Explain:

```text
Logged-in customers can continue ordering through the chatbot and see their orders in the customer portal.
```

### 7. WhatsApp Agent

Open:

```text
/dashboard/whatsapp-agent
```

Use mock inbound simulator:

```text
mujhe black hoodie large chahiye
```

Explain:

```text
Previously a person answered WhatsApp queries. Now the same AI agent can receive WhatsApp messages, answer using RAG, and prepare orders.
```

### 8. Transactions, Stock, and Payments

Open:

```text
/dashboard/transactions
/dashboard/payments
```

Explain:

```text
Orders reserve stock. Completed orders deduct stock. Cancelled orders release stock. Payments support COD/manual/local wallet style flows for FYP.
```

### 9. Reports and Owner Agent

Open:

```text
/dashboard/reports
/dashboard/owner-agent
```

Ask owner agent:

```text
What sold the most today?
Which items are low stock?
Give me promotion ideas.
Summarize customer chats.
```

Explain:

```text
The owner does not need to manually analyze business data. The owner-side AI assistant gives business summaries and recommendations.
```

## Demo Closing Line

```text
BizXusAI helps a small business go online, answer customers 24/7 in local language, take orders through chat/WhatsApp, manage stock and payments, and receive business insights from one generalized SaaS platform.
```
