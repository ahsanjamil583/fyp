# BizXusAI WhatsApp Bridge

This service connects a real WhatsApp or WhatsApp Business number through **Linked devices** using Baileys.

Flow:

1. Business owner saves WhatsApp Agent settings in BizXusAI with provider `Baileys linked device`.
2. The running bridge picks that business up from the API within seconds (see Tenant discovery).
3. Owner clicks **Open WhatsApp connection page** in the dashboard.
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
http://localhost:3005                 every business configured on this bridge
http://localhost:3005/pair/<tenantId> one business only
```

`/pair/<tenantId>` is what the dashboard's **Open WhatsApp connection page** button links
to, so an owner sees only their own QR code and never another tenant's card. Set
`WHATSAPP_BRIDGE_PUBLIC_URL` in `backend/.env` if the bridge is not on `localhost:3005`.

## Tenant discovery

Set `BIZXUS_BRIDGE_KEY` to the same value as `WHATSAPP_BRIDGE_ADMIN_KEY` on the API and
the bridge fetches its business list from `GET /whatsapp/bridge/tenants` every 30s
(`BIZXUS_DISCOVERY_INTERVAL_SECONDS`). A business joins when its owner saves WhatsApp
settings and leaves when they disconnect; a dashboard token refresh is picked up too. An
owner opening a pairing link for a business the bridge has not seen triggers an
immediate refresh, so the first click works.

Tenants listed in this `.env` are pinned: discovery never removes them. Without a bridge
key, only those listed tenants can pair.

## When WhatsApp unlinks the device

The pairing page recovers on its own: the dead credentials are deleted and a new QR
appears within a few seconds. The owner can also force this from the page with **Get a
new QR code**, which is also how they move the agent to a different WhatsApp number. No
one needs to delete `.baileys_auth/` by hand any more.

Important:

- Use one bridge process per business WhatsApp number.
- Use a separate `WHATSAPP_AUTH_PATH` for each business.
- Do not commit `.env` or `.baileys_auth`.
- Baileys is an unofficial WhatsApp Web approach. Use a dedicated/test business number and avoid spam/bulk messaging.
