# BizXusAI WhatsApp Bridge

This service connects a real WhatsApp or WhatsApp Business number through **Linked devices** using Baileys.

Flow:

1. Business owner saves WhatsApp Agent settings in BizXusAI with provider `Baileys linked device`.
2. Owner copies the bridge environment values from the dashboard.
3. Owner runs this bridge and opens the QR page.
4. Owner scans the QR from WhatsApp > Linked devices.
5. Customer messages the business WhatsApp number.
6. This bridge sends the inbound message to BizXusAI.
7. BizXusAI generates the AI reply using the same RAG/catalog/order brain.
8. This bridge sends the reply back from the connected WhatsApp number.

Run:

```powershell
cd whatsapp-bridge
Copy-Item .env.example .env
npm install
npm run dev
```

Open:

```text
http://localhost:3005
```

Important:

- Use one bridge process per business WhatsApp number.
- Use a separate `WHATSAPP_AUTH_PATH` for each business.
- Do not commit `.env` or `.baileys_auth`.
- Baileys is an unofficial WhatsApp Web approach. Use a dedicated/test business number and avoid spam/bulk messaging.
