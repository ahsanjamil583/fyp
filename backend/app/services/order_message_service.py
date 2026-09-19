"""Order confirmations over email and WhatsApp.

Two events, two different messages:

``order_placed``
    The order exists. Sent for every online order, whatever the payment method.
``payment_confirmed``
    Money arrived. Sent only when an order actually reaches a paid state, so a
    cash-on-delivery order never gets one - nothing has been paid yet.

Three rules run through the whole module, and each exists because of how this codebase
already behaves:

1. **A failed message never fails an order.** Every send is wrapped. The precedent is
   ``create_business_notification``, which swallows its own errors; the opposite
   precedent is ``start_payment_challenge``, which deliberately fails the payment when
   its OTP email fails. A confirmation is not like an OTP: the order is already real, and
   losing it because an SMTP server blinked would be absurd.

2. **Exactly once per (order, event, channel).** Gateway callbacks replay,
   ``_sync_transaction_payment_status`` runs on several paths, and customers retry. A
   delivery row is claimed with an upsert against a unique index *before* anything is
   sent, so a second attempt loses the race and sends nothing.

3. **WhatsApp is best-effort and conditional.** ``send_whatsapp_text`` does not actually
   deliver anything - it writes a row that the external Baileys bridge later claims. If
   the tenant has never paired a device, that row is never collected. So WhatsApp is
   attempted only when the integration is genuinely connected, and skipping is a normal
   outcome rather than an error anyone needs to see.
"""

from __future__ import annotations

import asyncio

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.db.mongodb import get_database
from app.integrations.whatsapp.provider import WhatsAppSendError, send_whatsapp_text
from app.services.email_service import EmailSendError, send_order_email
from app.services.localization_service import normalize_optional_email, normalize_optional_pk_phone_or_blank
from app.services.order_receipt_service import ensure_receipt_token

logger = logging.getLogger(__name__)

EVENT_ORDER_PLACED = "order_placed"
EVENT_PAYMENT_CONFIRMED = "payment_confirmed"
VALID_EVENTS = frozenset({EVENT_ORDER_PLACED, EVENT_PAYMENT_CONFIRMED})

CHANNEL_EMAIL = "email"
CHANNEL_WHATSAPP = "whatsapp"

DELIVERY_COLLECTION = "order_message_deliveries"
SETTINGS_COLLECTION = "order_message_settings"

# Counter sales hand over a printed slip at the till, so a confirmation would be noise.
# Imported rows are history and must never message anyone about a months-old order.
SILENT_SOURCES = frozenset({"cashier", "imported"})

# Sources where the recipient address was supplied by an unauthenticated caller and
# never verified. The public website order form takes a name, phone and email with no
# account behind them, so confirming an order there would let anyone make this platform
# send mail to any address, with attacker-controlled order content in the body.
#
# These still get their confirmation, just not on the strength of an anonymous form:
# it goes out once the money arrives (payment_confirmed), by which point the address
# has been used for a real transaction.
UNVERIFIED_RECIPIENT_SOURCES = frozenset({"website", "website_ai_chat"})

# Paid, or promised on delivery. "cod" counts as settled for the order's purposes but is
# not a payment, which is why it does not trigger a payment confirmation.
PAID_STATUSES = frozenset({"paid"})


# ------------------------------------------------------------------------ settings --


def default_message_settings(tenant_id: ObjectId) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "tenantId": tenant_id,
        "emailEnabled": True,
        "whatsappEnabled": True,
        "sendOnOrderPlaced": True,
        "sendOnPaymentConfirmed": True,
        "footerNote": "",
        "createdAt": now,
        "updatedAt": now,
    }


def serialize_message_settings(document: dict[str, Any] | None, tenant_id: ObjectId) -> dict[str, Any]:
    source = document or default_message_settings(tenant_id)
    return {
        "emailEnabled": bool(source.get("emailEnabled", True)),
        "whatsappEnabled": bool(source.get("whatsappEnabled", True)),
        "sendOnOrderPlaced": bool(source.get("sendOnOrderPlaced", True)),
        "sendOnPaymentConfirmed": bool(source.get("sendOnPaymentConfirmed", True)),
        "footerNote": str(source.get("footerNote") or "")[:300],
        "emailConfigured": bool(settings.smtp_host and settings.smtp_username and settings.smtp_password),
    }


async def get_message_settings(tenant_id: ObjectId) -> dict[str, Any]:
    db = get_database()
    document = await db[SETTINGS_COLLECTION].find_one({"tenantId": tenant_id})
    return serialize_message_settings(document, tenant_id)


async def update_message_settings(tenant_id: ObjectId, payload) -> dict[str, Any]:
    db = get_database()
    now = datetime.now(timezone.utc)
    update = {
        "emailEnabled": bool(payload.emailEnabled),
        "whatsappEnabled": bool(payload.whatsappEnabled),
        "sendOnOrderPlaced": bool(payload.sendOnOrderPlaced),
        "sendOnPaymentConfirmed": bool(payload.sendOnPaymentConfirmed),
        "footerNote": str(payload.footerNote or "").strip()[:300],
        "updatedAt": now,
    }
    await db[SETTINGS_COLLECTION].update_one(
        {"tenantId": tenant_id},
        {"$set": update, "$setOnInsert": {"tenantId": tenant_id, "createdAt": now}},
        upsert=True,
    )
    return await get_message_settings(tenant_id)


# ----------------------------------------------------------------------- recipients --


def resolve_recipients(transaction: dict[str, Any]) -> dict[str, str]:
    """Where a confirmation for this order should go.

    Read from the order's own snapshot, which is the one place that is populated for
    both a signed-in customer and a guest who checked out from the public site or over
    WhatsApp. A channel whose address is missing is simply skipped.
    """
    snapshot = transaction.get("customerSnapshot") or {}
    return {
        "name": str(snapshot.get("name") or "").strip(),
        "email": normalize_optional_email(snapshot.get("email") or ""),
        "phone": normalize_optional_pk_phone_or_blank(snapshot.get("phone") or ""),
    }


async def whatsapp_is_reachable(tenant_id: ObjectId) -> tuple[bool, str]:
    """Whether a WhatsApp message stands any chance of arriving.

    ``send_whatsapp_text`` always succeeds at writing its log row, so asking it is not a
    test of anything. What matters is whether a device is actually paired: with the mock
    provider, or an unconnected bridge, the row is never collected by anybody.
    """
    db = get_database()
    integration = await db.whatsapp_integrations.find_one({"tenantId": tenant_id})
    if not integration:
        return False, "no WhatsApp integration for this business"
    if str(integration.get("provider") or settings.whatsapp_provider).lower() == "mock":
        return False, "WhatsApp is in mock mode, so nothing would be delivered"
    # connectionStatus is derived on the API response and never persisted, so reading it
    # off the document always said "not connected" and no confirmation was ever sent.
    from app.services.whatsapp_service import whatsapp_connection_status

    connection_status = whatsapp_connection_status(integration)
    if connection_status != "connected":
        return False, f"WhatsApp is {connection_status.replace('_', ' ')}"
    return True, ""


async def whatsapp_budget_available(tenant_id: ObjectId) -> bool:
    """Respect the tenant's monthly WhatsApp allowance.

    A confirmation is worth less than a customer's reply going unanswered because the
    allowance was spent on notifications.
    """
    try:
        from app.core.module_guard import ensure_tenant_module_usage_available

        await ensure_tenant_module_usage_available(tenant_id, "whatsapp_agent")
        return True
    except Exception:
        return False


# ------------------------------------------------------------------------ templates --

# Named rather than inlined so message bodies are built by joining a list of lines,
# which keeps them readable and avoids escape-heavy string literals.
NEWLINE = "\n"


def _money(value: Any, currency: str = "PKR") -> str:
    try:
        return f"{currency} {float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return f"{currency} 0.00"


def receipt_url(token: str) -> str:
    """The link that goes in the message.

    Points at the API, not the web client: the receipt is server-rendered HTML served
    from ``/receipts/{token}``, and there is no page in the React app behind that path.
    Reuses the gateway helper so a receipt link and a payment return URL always agree on
    which address the outside world can reach this server on.
    """
    from app.integrations.payments.gateways import _api_base_url

    return f"{_api_base_url()}/receipts/{token}"


def _item_lines(transaction, currency: str) -> str:
    rows = []
    for line in transaction.get("items") or []:
        name = str(line.get("name") or "Item")
        variant = str(line.get("selectedVariantName") or "").strip()
        label = f"{name} ({variant})" if variant else name
        rows.append(f"  - {line.get('quantity', 1)} x {label}   {_money(line.get('subtotal'), currency)}")
    return NEWLINE.join(rows) or "  - (no items recorded)"


def build_message_content(
    event: str,
    tenant: dict[str, Any],
    transaction: dict[str, Any],
    recipients: dict[str, str],
    receipt_link: str,
    footer_note: str = "",
) -> dict[str, str]:
    """One set of words per event, rendered for both channels.

    English only, deliberately: a half-translated confirmation reads worse than a clear
    English one, and this codebase's Roman Urdu support is tuned for conversational
    replies rather than transactional documents.

    WhatsApp gets its own short version. The email body is plain text here; the HTML
    version is built in ``email_service`` from the same fields.
    """
    business = str(tenant.get("name") or "the business")
    number = str(transaction.get("transactionNumber") or "your order")
    pricing = transaction.get("pricing") or {}
    currency = pricing.get("currency") or "PKR"
    total = _money(pricing.get("total"), currency)
    greeting = f"Hi {recipients['name']}," if recipients.get("name") else "Hi,"
    items = _item_lines(transaction, currency)

    if event == EVENT_ORDER_PLACED:
        subject = f"{business}: order {number} received"
        headline = "We have your order"
        intro = f"Thanks for ordering from {business}. Your order {number} has been received."
        status_line = (
            "Payment is complete."
            if str(transaction.get("paymentStatus")) == "paid"
            else "You can complete payment from your order page."
        )
        whatsapp = NEWLINE.join([
            greeting,
            f"{business} received your order {number}.",
            f"Total: {total}",
            status_line,
            f"Receipt: {receipt_link}",
        ])
    else:
        subject = f"{business}: payment received for {number}"
        headline = "Payment received"
        intro = f"{business} has received your payment for order {number}. Thank you."
        status_line = "Your order is now marked as paid."
        whatsapp = NEWLINE.join([
            greeting,
            f"{business} received your payment for {number}.",
            f"Amount: {total}",
            f"Receipt: {receipt_link}",
        ])

    body_parts = [
        greeting,
        "",
        intro,
        "",
        f"Order: {number}",
        items,
        "",
        f"Total: {total}",
        status_line,
        "",
        "View or print your receipt:",
        receipt_link,
    ]
    if footer_note:
        body_parts += ["", footer_note]
    body_parts += ["", "Regards,", business]

    return {
        "subject": subject,
        "headline": headline,
        "intro": intro,
        "statusLine": status_line,
        "itemLines": items,
        "text": NEWLINE.join(body_parts),
        "whatsapp": whatsapp.strip(),
        "total": total,
        "orderNumber": number,
        "receiptLink": receipt_link,
        "footerNote": footer_note,
    }


# ------------------------------------------------------------------- delivery claim --


async def _claim_delivery(transaction: dict[str, Any], event: str, channel: str, target: str) -> bool:
    """Reserve the right to send, or report that someone already did.

    The claim is written before the send, not after. Doing it afterwards would leave a
    window where a replayed callback sends a second copy while the first is still in
    flight, which is exactly the failure this is meant to prevent.
    """
    db = get_database()
    now = datetime.now(timezone.utc)
    try:
        await db[DELIVERY_COLLECTION].insert_one(
            {
                "tenantId": transaction["tenantId"],
                "transactionId": transaction["_id"],
                "transactionNumber": transaction.get("transactionNumber", ""),
                "event": event,
                "channel": channel,
                "target": target,
                "status": "claimed",
                "createdAt": now,
                "updatedAt": now,
            }
        )
        return True
    except DuplicateKeyError:
        return False


async def _finish_delivery(transaction: dict[str, Any], event: str, channel: str, status_value: str, detail: str = "") -> None:
    db = get_database()
    await db[DELIVERY_COLLECTION].update_one(
        {"transactionId": transaction["_id"], "event": event, "channel": channel},
        {"$set": {"status": status_value, "detail": detail[:300], "updatedAt": datetime.now(timezone.utc)}},
    )


# ----------------------------------------------------------------------- the sender --


async def send_order_message(transaction: dict[str, Any], event: str, tenant: dict[str, Any] | None = None) -> dict[str, Any]:
    """Send one event's confirmation on every channel that is available and enabled.

    Returns a report rather than raising. The caller is an order-creation or
    payment-settlement path, and nothing here is important enough to break either.
    """
    report: dict[str, Any] = {"event": event, "sent": [], "skipped": [], "failed": []}
    if event not in VALID_EVENTS:
        report["skipped"].append({"channel": "all", "reason": f"unknown event {event}"})
        return report

    source = str(transaction.get("source") or "")
    if source in SILENT_SOURCES:
        report["skipped"].append({"channel": "all", "reason": f"{source} orders are not messaged"})
        return report

    if event == EVENT_ORDER_PLACED and source in UNVERIFIED_RECIPIENT_SOURCES:
        report["skipped"].append(
            {"channel": "all", "reason": "guest order: the contact details are unverified until the order is paid"}
        )
        return report

    db = get_database()
    tenant = tenant or await db.tenants.find_one({"_id": transaction["tenantId"]})
    if not tenant:
        report["skipped"].append({"channel": "all", "reason": "tenant not found"})
        return report

    config = await get_message_settings(transaction["tenantId"])
    if event == EVENT_ORDER_PLACED and not config["sendOnOrderPlaced"]:
        report["skipped"].append({"channel": "all", "reason": "order-placed messages are switched off"})
        return report
    if event == EVENT_PAYMENT_CONFIRMED and not config["sendOnPaymentConfirmed"]:
        report["skipped"].append({"channel": "all", "reason": "payment messages are switched off"})
        return report

    recipients = resolve_recipients(transaction)
    token = await ensure_receipt_token(transaction)
    content = build_message_content(event, tenant, transaction, recipients, receipt_url(token), config["footerNote"])

    # ----------------------------------------------------------------- email --
    if not config["emailEnabled"]:
        report["skipped"].append({"channel": CHANNEL_EMAIL, "reason": "email is switched off for this business"})
    elif not recipients["email"]:
        report["skipped"].append({"channel": CHANNEL_EMAIL, "reason": "no email address on this order"})
    elif not config["emailConfigured"]:
        report["skipped"].append({"channel": CHANNEL_EMAIL, "reason": "SMTP is not configured"})
    elif not await _claim_delivery(transaction, event, CHANNEL_EMAIL, recipients["email"]):
        report["skipped"].append({"channel": CHANNEL_EMAIL, "reason": "already sent"})
    else:
        try:
            # Blocking SMTP inside order creation: a slow mail server stalled every
            # request on the server until it timed out.
            await asyncio.to_thread(
                send_order_email, to_email=recipients["email"], content=content, business_name=tenant.get("name", "")
            )
            await _finish_delivery(transaction, event, CHANNEL_EMAIL, "sent")
            report["sent"].append({"channel": CHANNEL_EMAIL, "target": recipients["email"]})
        except (EmailSendError, Exception) as exc:  # never break the order
            await _finish_delivery(transaction, event, CHANNEL_EMAIL, "failed", str(exc))
            logger.warning("Order confirmation email failed for %s: %s", transaction.get("transactionNumber"), type(exc).__name__)
            report["failed"].append({"channel": CHANNEL_EMAIL, "reason": type(exc).__name__})

    # -------------------------------------------------------------- whatsapp --
    if not config["whatsappEnabled"]:
        report["skipped"].append({"channel": CHANNEL_WHATSAPP, "reason": "WhatsApp is switched off for this business"})
        return report
    if not recipients["phone"]:
        report["skipped"].append({"channel": CHANNEL_WHATSAPP, "reason": "no phone number on this order"})
        return report

    reachable, why_not = await whatsapp_is_reachable(transaction["tenantId"])
    if not reachable:
        # A normal outcome, not a failure: most businesses never pair a device.
        report["skipped"].append({"channel": CHANNEL_WHATSAPP, "reason": why_not})
        return report
    if not await whatsapp_budget_available(transaction["tenantId"]):
        report["skipped"].append({"channel": CHANNEL_WHATSAPP, "reason": "monthly WhatsApp allowance is spent"})
        return report
    if not await _claim_delivery(transaction, event, CHANNEL_WHATSAPP, recipients["phone"]):
        report["skipped"].append({"channel": CHANNEL_WHATSAPP, "reason": "already sent"})
        return report

    try:
        await send_whatsapp_text(
            tenant_id=transaction["tenantId"],
            to_phone=recipients["phone"],
            message_text=content["whatsapp"],
            provider=settings.whatsapp_provider,
            raw_context={"source": "order_confirmation", "event": event, "transactionNumber": content["orderNumber"]},
        )
        await _finish_delivery(transaction, event, CHANNEL_WHATSAPP, "queued")
        report["sent"].append({"channel": CHANNEL_WHATSAPP, "target": recipients["phone"]})
    except (WhatsAppSendError, Exception):
        await _finish_delivery(transaction, event, CHANNEL_WHATSAPP, "failed")
        logger.warning("Order confirmation WhatsApp failed for %s.", transaction.get("transactionNumber"))
        report["failed"].append({"channel": CHANNEL_WHATSAPP, "reason": "whatsapp_send_failed"})

    return report


async def notify_order_placed(transaction: dict[str, Any], tenant: dict[str, Any] | None = None) -> dict[str, Any]:
    """Safe to call from any order-creation path. Never raises."""
    try:
        return await send_order_message(transaction, EVENT_ORDER_PLACED, tenant)
    except Exception:
        logger.exception("Order-placed confirmation failed for %s.", transaction.get("transactionNumber"))
        return {"event": EVENT_ORDER_PLACED, "sent": [], "skipped": [], "failed": [{"channel": "all", "reason": "unhandled"}]}


async def notify_payment_confirmed(transaction: dict[str, Any], tenant: dict[str, Any] | None = None) -> dict[str, Any]:
    """Safe to call whenever a payment status is recomputed. Never raises."""
    try:
        if str(transaction.get("paymentStatus")) not in PAID_STATUSES:
            return {"event": EVENT_PAYMENT_CONFIRMED, "sent": [], "skipped": [{"channel": "all", "reason": "not paid"}], "failed": []}
        return await send_order_message(transaction, EVENT_PAYMENT_CONFIRMED, tenant)
    except Exception:
        logger.exception("Payment confirmation failed for %s.", transaction.get("transactionNumber"))
        return {"event": EVENT_PAYMENT_CONFIRMED, "sent": [], "skipped": [], "failed": [{"channel": "all", "reason": "unhandled"}]}
