> **Superseded.** This phase documented the Meta WhatsApp Cloud API integration, which
> was replaced by the Baileys linked-device bridge in `whatsapp-bridge/`. The webhook
> routes described here no longer exist and the provider now accepts only `mock` or
> `baileys`. Kept for project history; see the "WhatsApp Bridge" section of `README.md`
> for the current setup.

# Phase H — Live WhatsApp AI/RAG/Catalog/Order Agent Replies

## Goal

Phase H connects routed Meta WhatsApp webhook messages to the real BizXusAI customer agent behavior. After Phase G routes an incoming WhatsApp webhook by `metadata.phone_number_id`, Phase H makes the routed message behave like a real business agent conversation:

- identify the correct tenant/business
- use that tenant's catalog, RAG knowledge base, stock, payment settings, and conversation context
- produce short mobile-friendly WhatsApp replies
- create draft orders from WhatsApp messages
- collect missing details such as delivery/pickup, address, and city
- confirm the order from WhatsApp after customer confirmation
- create a transaction, reserve stock, save conversation history, and notify the owner

## Customer WhatsApp order flow

Example:

1. Customer: `2 spicy zinger burgers order kar do`
2. Agent: prepares a draft and asks delivery or pickup.
3. Customer: `delivery`
4. Agent: asks for address and city.
5. Customer: `House 12, Main Road, Attock`
6. Agent: asks for final confirmation.
7. Customer: `confirm`
8. Agent: creates the WhatsApp transaction, reserves stock, clears the draft, and replies with the order number.

## What was added

- WhatsApp draft context manager
- WhatsApp short confirmation detection such as `g`, `ji`, `yes`, `confirm`, `kar do`
- Draft cancellation detection such as `cancel`, `nahi chahiye`, `no`
- Delivery/pickup detail extraction
- Basic address and city extraction for WhatsApp text
- WhatsApp transaction creation from pending draft
- Stock reservation through existing inventory workflow
- Owner notification after WhatsApp order confirmation
- Short WhatsApp confirmation message formatting
- Dashboard Phase H status panel
- Mock simulator now supports the sequence needed to test a WhatsApp order
- Backend tests for Phase H helper behavior

## Important notes

- The agent only confirms an order after a pending draft exists and required details are available.
- If the business category requires delivery address/city, the agent asks for those details before confirmation.
- If the customer asks for a human, the handoff logic still takes priority.
- If the business owner disables agent or auto-reply, Phase H will not auto-confirm orders.
- Meta mode still requires the business number to complete Embedded Signup, webhook subscription, phone registration, and routing readiness.

## Testing checklist

Mock mode:

1. Open `/dashboard/whatsapp-agent`.
2. Use mock inbound message: `2 zinger burgers order kar do`.
3. Send: `delivery`.
4. Send: `House 12, Main Road, Attock`.
5. Send: `confirm`.
6. Confirm the reply contains an order number.
7. Open Transactions and confirm the new WhatsApp transaction appears.
8. Confirm inventory reservation is applied.

Real Meta mode:

1. Complete Phases A-G.
2. Confirm Phase H panel shows Live ready.
3. From a real customer WhatsApp number, message the connected business WhatsApp number.
4. Ask a catalog/RAG question.
5. Create and confirm an order using the same message sequence above.
6. Confirm the transaction appears in the owner dashboard.
