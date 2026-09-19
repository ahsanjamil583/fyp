from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from html import escape
from typing import Any
from urllib.parse import urljoin

import httpx
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from fastapi import HTTPException, status

from app.core.config import settings
from app.integrations.payments import gateways, providers
from app.integrations.payments.provider_base import FLOW_OTP, FLOW_REDIRECT, PaymentContext, PaymentProviderError
from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.private_uploads import payment_record_view
from app.core.public_views import customer_order_view
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.business_notification_service import create_business_notification
from app.services.inventory_service import restore_transaction_stock
from app.services.customer_notification_service import create_customer_notification
from app.services.storage_service import store_payment_proof_image
from app.services.transaction_workflow_service import get_allowed_payment_statuses
from app.services import payment_otp_service
from app.services.localization_service import normalize_optional_pk_phone

logger = logging.getLogger(__name__)

PAYMENT_METHODS = {"cod", "manual_bank", "bank_transfer", "jazzcash_mock", "easypaisa_mock", "stripe_test", "manual", "jazzcash", "easypaisa", "stripe", "card", "online_card"}
# The *_mock codes are the owner-verified manual flows and stay valid so historical
# records keep rendering. "jazzcash"/"easypaisa" are the redirect gateways added later.
CANONICAL_PAYMENT_METHODS = {"cod", "manual_bank", "jazzcash_mock", "easypaisa_mock", "stripe_test", "jazzcash", "easypaisa"}
ONLINE_GATEWAY_METHODS = {"jazzcash": "jazzcash", "easypaisa": "easypaisa"}
# Saved settings from before the gateways existed point at the manual codes.
LEGACY_METHOD_UPGRADES = {"jazzcash_mock": "jazzcash", "easypaisa_mock": "easypaisa"}
PAYMENT_METHOD_ALIASES = {
    "manual": "manual_bank",
    "bank": "manual_bank",
    "bank_transfer": "manual_bank",
    "manual_transfer": "manual_bank",
    "jazz_cash": "jazzcash",
    "easy_paisa": "easypaisa",
    "stripe": "stripe_test",
    "card": "stripe_test",
    "online_card": "stripe_test",
}
PAYMENT_RECORD_STATUSES = {"pending_verification", "paid", "rejected", "refunded", "cod", "pending", "completed", "failed"}
PAYMENT_STATUS_ALIASES = {
    "pending": "pending_verification",
    "completed": "paid",
    "complete": "paid",
    "verified": "paid",
    "failed": "rejected",
    "declined": "rejected",
    "cash_on_delivery": "cod",
}
PAYABLE_TRANSACTION_TYPES = {"order", "booking_request", "quote_request"}


def _format_receipt_money(value: Any, currency: str = "PKR") -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{escape(str(currency or 'PKR'))} {amount:,.2f}"


def _format_receipt_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return escape(str(value or "-"))


def _receipt_text(value: Any, default: str = "-") -> str:
    text = str(value if value not in [None, ""] else default)
    return escape(text)


def _default_settings(tenant_id: ObjectId, actor_user_id: ObjectId | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "tenantId": tenant_id,
        "codEnabled": True,
        "manualEnabled": True,
        "bankTransferEnabled": True,
        "jazzCashEnabled": False,
        "easyPaisaEnabled": False,
        "stripeEnabled": False,
        "paymentsDemoMode": True,
        "requireOwnerApproval": True,
        "bankName": "",
        "jazzCashNumber": "",
        "jazzCashAccountTitle": "",
        "easyPaisaNumber": "",
        "easyPaisaAccountTitle": "",
        "bankAccountTitle": "",
        "bankAccountNumber": "",
        "bankIban": "",
        "defaultMethod": "cod",
        "customerInstructions": "Cash on delivery is available. Bank transfer, JazzCash, and EasyPaisa can be enabled for owner-verified demo payments.",
        "createdBy": actor_user_id,
        "createdAt": now,
        "updatedAt": now,
    }


def _normalize_method(method: str | None) -> str:
    normalized = str(method or "cod").strip().lower().replace(" ", "_")
    normalized = PAYMENT_METHOD_ALIASES.get(normalized, normalized)
    if normalized not in CANONICAL_PAYMENT_METHODS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid payment method.")
    return normalized


def _normalize_record_status(value: str | None) -> str:
    normalized = str(value or "paid").strip().lower()
    normalized = PAYMENT_STATUS_ALIASES.get(normalized, normalized)
    if normalized not in PAYMENT_RECORD_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid payment record status.")
    return normalized


def _public_method_label(method: str) -> str:
    return {
        "cod": "Cash on Delivery",
        "manual_bank": "Manual bank transfer",
        "jazzcash_mock": "JazzCash (manual)",
        "easypaisa_mock": "EasyPaisa (manual)",
        "jazzcash": "JazzCash",
        "easypaisa": "Easypaisa",
        "stripe_test": "Stripe (card)",
    }.get(method, method.replace("_", " ").title())


def _gateway_available(provider: str) -> bool:
    """True when this gateway can take a customer end to end right now.

    Delegates to the provider so there is one answer to this question, whichever flow
    the gateway is configured for.
    """
    try:
        return providers.get_provider(provider).is_available()
    except PaymentProviderError:
        return False


def _wallet_method_code(provider: str, *, allow_otp: bool) -> str:
    """Which method code a wallet offers right now.

    A wallet in OTP mode needs a signed-in customer: the code goes to the address on
    their account, and a guest has no account. Rather than dead-ending them, a guest is
    offered the manual variant of the same wallet - pay from your own app, then share the
    transaction ID for the owner to verify - which needs no account at all.
    """
    if not _gateway_available(provider):
        return f"{provider}_mock"
    if providers.is_otp_provider(provider) and not allow_otp:
        return f"{provider}_mock"
    return provider


def _enabled_method_codes(settings_doc: dict, *, allow_otp: bool = True) -> list[str]:
    methods: list[str] = []
    if settings_doc.get("codEnabled"):
        methods.append("cod")
    if settings_doc.get("manualEnabled") or settings_doc.get("bankTransferEnabled"):
        methods.append("manual_bank")
    # One toggle per wallet. Whether the customer is redirected to the gateway, asked for
    # an emailed code, or told to pay manually depends on the gateway's configured mode
    # and on whether there is an account behind this checkout.
    if settings_doc.get("jazzCashEnabled"):
        methods.append(_wallet_method_code("jazzcash", allow_otp=allow_otp))
    if settings_doc.get("easyPaisaEnabled"):
        methods.append(_wallet_method_code("easypaisa", allow_otp=allow_otp))
    # Offering Stripe without a secret key puts a button in front of the customer that
    # can only fail at payment time, the same trap the gateways avoid above.
    if settings_doc.get("stripeEnabled") and settings.stripe_secret_key:
        methods.append("stripe_test")
    return methods


def serialize_payment_settings(settings_doc: dict) -> dict:
    serialized = serialize_document(settings_doc)
    enabled = _enabled_method_codes(settings_doc)
    serialized["enabledMethods"] = [{"code": method, "label": _public_method_label(method)} for method in enabled]
    serialized["localPaymentsEnabled"] = bool(enabled)
    serialized["stripeConfigured"] = bool(settings.stripe_secret_key)
    serialized["stripeWebhookConfigured"] = bool(settings.stripe_webhook_secret)
    serialized["stripeCurrency"] = settings.stripe_currency.upper()
    serialized["stripePublishableKey"] = settings.stripe_publishable_key
    return serialized


def _method_customer_details(settings_doc: dict, method: str) -> dict[str, Any]:
    if method == "cod":
        return {
            "code": method,
            "label": _public_method_label(method),
            "description": "Pay cash when your order is delivered or picked up.",
            "requiresOwnerApproval": False,
            "accountTitle": "",
            "accountNumber": "",
            "bankName": "",
            "iban": "",
        }
    if method == "manual_bank":
        return {
            "code": method,
            "label": _public_method_label(method),
            "description": "Transfer the amount, then share the reference with the business for verification.",
            "requiresOwnerApproval": True,
            "accountTitle": settings_doc.get("bankAccountTitle", ""),
            "accountNumber": settings_doc.get("bankAccountNumber", ""),
            "bankName": settings_doc.get("bankName", ""),
            "iban": settings_doc.get("bankIban", ""),
        }
    if method == "jazzcash_mock":
        return {
            "code": method,
            "label": _public_method_label(method),
            "description": "Send payment through JazzCash, then share the transaction ID for owner verification.",
            "requiresOwnerApproval": True,
            "accountTitle": settings_doc.get("jazzCashAccountTitle", ""),
            "accountNumber": settings_doc.get("jazzCashNumber", ""),
            "bankName": "JazzCash",
            "iban": "",
        }
    if method == "easypaisa_mock":
        return {
            "code": method,
            "label": _public_method_label(method),
            "description": "Send payment through EasyPaisa, then share the transaction ID for owner verification.",
            "requiresOwnerApproval": True,
            "accountTitle": settings_doc.get("easyPaisaAccountTitle", ""),
            "accountNumber": settings_doc.get("easyPaisaNumber", ""),
            "bankName": "EasyPaisa",
            "iban": "",
        }
    if method in ONLINE_GATEWAY_METHODS:
        # The provider describes itself, so a wallet in OTP mode advertises the code flow
        # and a wallet in redirect mode advertises the redirect, from one source.
        descriptor = providers.get_provider(method).descriptor()
        return {**descriptor, "code": method, "label": _public_method_label(method)}

    if method == "stripe_test":
        descriptor = providers.StripeProvider().descriptor()
        return {**descriptor, "code": method, "label": _public_method_label(method)}
    return {"code": method, "label": _public_method_label(method), "description": "", "requiresOwnerApproval": True}


def serialize_customer_payment_options(settings_doc: dict | None, *, allow_otp: bool = True) -> dict[str, Any]:
    settings_doc = settings_doc or {}
    if not settings_doc:
        settings_doc = _default_settings(ObjectId())
    enabled = _enabled_method_codes(settings_doc, allow_otp=allow_otp)
    methods = [_method_customer_details(settings_doc, method) for method in enabled]
    default_method = settings_doc.get("defaultMethod") or (enabled[0] if enabled else "cod")
    if default_method not in enabled and enabled:
        # A tenant whose saved default predates the redirect gateways should land on the
        # same wallet, not silently fall back to cash on delivery.
        upgraded = LEGACY_METHOD_UPGRADES.get(default_method)
        default_method = upgraded if upgraded in enabled else enabled[0]
    return {
        "enabled": bool(methods),
        "defaultMethod": default_method,
        "methods": methods,
        "customerInstructions": settings_doc.get("customerInstructions", ""),
        "paymentsDemoMode": bool(settings_doc.get("paymentsDemoMode", True)),
        "requireOwnerApproval": bool(settings_doc.get("requireOwnerApproval", True)),
    }


async def get_customer_payment_options_for_tenant(tenant_oid: ObjectId, *, allow_otp: bool = True) -> dict[str, Any]:
    """Payment methods this business offers.

    ``allow_otp`` is False for anonymous checkouts (the public website), where there is
    no account to email a code to. See :func:`_wallet_method_code`.
    """
    db = get_database()
    settings = await db.payment_settings.find_one({"tenantId": tenant_oid})
    if not settings:
        settings = _default_settings(tenant_oid)
        settings["_id"] = (await db.payment_settings.insert_one(settings)).inserted_id
    return serialize_customer_payment_options(settings, allow_otp=allow_otp)


def normalize_customer_payment_preference(payment_method: str | None, payment_options: dict[str, Any]) -> dict[str, Any]:
    methods = payment_options.get("methods") or []
    enabled_codes = {method["code"] for method in methods}
    selected = _normalize_method(payment_method or payment_options.get("defaultMethod") or "cod")
    if selected not in enabled_codes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected payment method is not enabled for this business.")
    selected_method = next((method for method in methods if method["code"] == selected), {"code": selected, "label": _public_method_label(selected)})
    return {
        "method": selected,
        "methodLabel": selected_method.get("label", _public_method_label(selected)),
        "requiresOwnerApproval": bool(selected_method.get("requiresOwnerApproval", True)),
        "instructions": payment_options.get("customerInstructions", ""),
        "selectedAt": datetime.now(timezone.utc),
    }


# Fields the owner writes for themselves, which must never reach the customer.
_OWNER_ONLY_RECORD_FIELDS = (
    "actorUserId",
    "createdBy",
    "updatedBy",
    "verifiedBy",
    "internalNotes",
    "providerResponse",
    "gatewayResponse",
    "ownerDecisionNotes",
    # `notes` carries the provider's raw failure text, which is the same account and
    # parameter detail that was deliberately kept out of the HTTP error body.
    "notes",
)
_OWNER_ONLY_VERIFICATION_FIELDS = (
    "verifiedByUserId",
    "rejectedByUserId",
    "submittedByCustomerUserId",
    "decisionNotes",
)


def _customer_safe_payment_record(record: dict | None) -> dict | None:
    """A payment record with the owner's private fields removed.

    Both customer-facing serializers go through this, so a field added to one strip list
    cannot be forgotten in the other.
    """
    view = payment_record_view(record)
    if not view:
        return view
    for key in _OWNER_ONLY_RECORD_FIELDS:
        view.pop(key, None)
    verification = view.get("verification")
    if isinstance(verification, dict):
        for key in _OWNER_ONLY_VERIFICATION_FIELDS:
            verification.pop(key, None)
    return view


async def list_customer_payment_records_for_transaction(transaction: dict) -> list[dict[str, Any]]:
    db = get_database()
    cursor = db.payment_records.find({"transactionId": transaction["_id"]}).sort("createdAt", -1)
    return [_customer_safe_payment_record(record) async for record in cursor]


async def summarize_payment_records_for_transaction(transaction: dict, db=None, *, for_customer: bool = False) -> dict[str, Any]:
    """Payment-proof summary for one order.

    `for_customer` decides whether `latest` is stripped of the owner's private fields.
    It defaults to False because most callers here are owner-facing — the transactions
    list, the order detail and the payments dashboard all render these notes deliberately
    — and stripping unconditionally quietly removed the owner's own decision notes from
    their own screens.
    """
    db = db if db is not None else get_database()
    empty_summary = {
        "latest": None,
        "pendingCount": 0,
        "approvedCount": 0,
        "rejectedCount": 0,
        "refundCount": 0,
        "hasPendingProof": False,
        "hasRejectedProof": False,
        "hasApprovedPayment": False,
        "needsOwnerReview": False,
    }
    if not hasattr(db, "payment_records"):
        return empty_summary
    records = await db.payment_records.find({"transactionId": transaction["_id"]}).sort("createdAt", -1).to_list(length=None)
    payments = [record for record in records if record.get("recordType") == "payment"]
    latest = payments[0] if payments else None
    pending = [record for record in payments if record.get("status") in {"pending_verification", "pending"}]
    approved = [record for record in payments if record.get("status") in {"paid", "completed"}]
    rejected = [record for record in payments if record.get("status") in {"rejected", "failed"}]
    refunds = [record for record in records if record.get("recordType") == "refund" or record.get("status") == "refunded"]
    return {
        **empty_summary,
        # Stripped only for the customer. Served on their own orders list and order
        # detail, where it used to return the owner's private decision notes and the
        # internal actor ids unfiltered.
        "latest": (_customer_safe_payment_record(latest) if for_customer else payment_record_view(latest)) if latest else None,
        "pendingCount": len(pending),
        "approvedCount": len(approved),
        "rejectedCount": len(rejected),
        "refundCount": len(refunds),
        "hasPendingProof": bool(pending),
        "hasRejectedProof": bool(rejected),
        "hasApprovedPayment": bool(approved),
        "needsOwnerReview": bool(pending),
    }


def _build_payment_receipt_html(tenant: dict, transaction: dict, record: dict) -> str:
    tenant_name = _receipt_text(tenant.get("name"), "BizXusAI Business")
    tenant_city = _receipt_text((tenant.get("address") or {}).get("city"), "Online")
    tenant_phone = _receipt_text((tenant.get("contact") or {}).get("phone"), "-")
    customer = transaction.get("customerSnapshot") or record.get("customerSnapshot") or {}
    currency = record.get("currency") or (transaction.get("pricing") or {}).get("currency") or "PKR"
    transaction_total = (transaction.get("pricing") or {}).get("total") or transaction.get("totalAmount") or record.get("amount") or 0
    receipt_number = f"RCPT-{str(record.get('_id'))[-8:].upper()}"
    status_label = _receipt_text(str(record.get("status", "")).replace("_", " ").title(), "Recorded")
    record_type = _receipt_text(str(record.get("recordType", "payment")).replace("_", " ").title(), "Payment")
    items = transaction.get("items") or []
    item_rows = ""
    for item in items:
        options = item.get("selectedOptions") or item.get("options") or {}
        option_text = ", ".join(f"{key}: {value}" for key, value in options.items() if value) if isinstance(options, dict) else ""
        item_rows += f"""
          <tr>
            <td>
              <strong>{_receipt_text(item.get('name'), 'Item')}</strong>
              <div class="muted">{_receipt_text(option_text, '')}</div>
            </td>
            <td>{_receipt_text(item.get('quantity'), '1')}</td>
            <td>{_format_receipt_money(item.get('unitPrice') or item.get('price') or 0, currency)}</td>
            <td>{_format_receipt_money(item.get('subtotal') or 0, currency)}</td>
          </tr>
        """
    if not item_rows:
        item_rows = """
          <tr>
            <td colspan="4" class="muted">No line items were captured for this transaction.</td>
          </tr>
        """

    reference = record.get("referenceNumber") or record.get("providerPaymentIntentId") or record.get("providerSessionId") or "-"
    notes = record.get("notes") or "-"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{receipt_number} - BizXusAI Receipt</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #0f172a;
      --muted: #64748b;
      --line: #dbe4f0;
      --brand: #2563eb;
      --soft: #eff6ff;
      --paid: #15803d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #eef4fb;
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    .page {{
      width: min(900px, calc(100% - 32px));
      margin: 32px auto;
      border: 1px solid var(--line);
      border-radius: 28px;
      background: white;
      box-shadow: 0 24px 80px rgba(15, 23, 42, 0.12);
      overflow: hidden;
    }}
    .hero {{
      display: grid;
      gap: 24px;
      grid-template-columns: 1fr auto;
      padding: 34px;
      background: linear-gradient(135deg, #f8fbff, #eaf2ff);
      border-bottom: 1px solid var(--line);
    }}
    .eyebrow {{
      color: var(--brand);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.22em;
      text-transform: uppercase;
    }}
    h1 {{ margin: 8px 0 0; font-size: 34px; line-height: 1.05; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      background: #dcfce7;
      color: var(--paid);
      font-size: 13px;
      font-weight: 800;
      padding: 9px 14px;
      white-space: nowrap;
    }}
    .content {{ padding: 30px 34px 36px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .card {{ border: 1px solid var(--line); border-radius: 20px; padding: 18px; background: #fff; }}
    .label {{ color: var(--muted); font-size: 12px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; }}
    .value {{ margin-top: 7px; font-size: 16px; font-weight: 700; }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 18px; overflow: hidden; border: 1px solid var(--line); border-radius: 18px; }}
    th, td {{ padding: 14px 16px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: #f8fafc; color: var(--muted); font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; }}
    tr:last-child td {{ border-bottom: 0; }}
    .total {{
      display: grid;
      gap: 10px;
      margin-top: 18px;
      margin-left: auto;
      max-width: 360px;
    }}
    .total-row {{ display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--line); padding-bottom: 10px; }}
    .total-row strong {{ font-size: 18px; }}
    .actions {{ display: flex; justify-content: flex-end; gap: 10px; padding: 0 34px 34px; }}
    button {{ border: 0; border-radius: 999px; background: var(--brand); color: white; cursor: pointer; font-weight: 800; padding: 12px 18px; }}
    .footer {{ padding: 18px 34px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }}
    @media (max-width: 720px) {{
      .hero, .grid {{ grid-template-columns: 1fr; }}
      .hero, .content, .actions, .footer {{ padding-left: 20px; padding-right: 20px; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
    @media print {{
      body {{ background: white; }}
      .page {{ width: 100%; margin: 0; border-radius: 0; box-shadow: none; border: 0; }}
      .actions {{ display: none; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div>
        <div class="eyebrow">BizXusAI Receipt</div>
        <h1>{receipt_number}</h1>
        <div class="muted">Generated for {tenant_name} on {_format_receipt_date(datetime.now(timezone.utc))}</div>
      </div>
      <div class="badge">{status_label}</div>
    </section>
    <section class="content">
      <div class="grid">
        <div class="card">
          <div class="label">Business</div>
          <div class="value">{tenant_name}</div>
          <div class="muted">{tenant_city} | {tenant_phone}</div>
        </div>
        <div class="card">
          <div class="label">Customer</div>
          <div class="value">{_receipt_text(customer.get('name'), 'Guest customer')}</div>
          <div class="muted">{_receipt_text(customer.get('phone'), '-')} | {_receipt_text(customer.get('email'), '-')}</div>
        </div>
        <div class="card">
          <div class="label">Transaction</div>
          <div class="value">{_receipt_text(transaction.get('transactionNumber'), '-')}</div>
          <div class="muted">{_receipt_text(transaction.get('transactionType'), 'order')} | {_receipt_text(transaction.get('status'), '-')}</div>
        </div>
        <div class="card">
          <div class="label">{record_type}</div>
          <div class="value">{_receipt_text(record.get('methodLabel') or _public_method_label(record.get('method', 'cod')))}</div>
          <div class="muted">Reference: {_receipt_text(reference)}</div>
        </div>
      </div>
      <table>
        <thead>
          <tr><th>Item</th><th>Qty</th><th>Unit</th><th>Subtotal</th></tr>
        </thead>
        <tbody>{item_rows}</tbody>
      </table>
      <div class="total">
        <div class="total-row"><span>Transaction total</span><strong>{_format_receipt_money(transaction_total, currency)}</strong></div>
        <div class="total-row"><span>{record_type} amount</span><strong>{_format_receipt_money(record.get('amount'), currency)}</strong></div>
      </div>
      <div class="card" style="margin-top:18px">
        <div class="label">Notes</div>
        <div class="value" style="font-size:14px;font-weight:600">{_receipt_text(notes)}</div>
        <div class="muted">Recorded at {_format_receipt_date(record.get('createdAt'))}</div>
      </div>
    </section>
    <section class="actions">
      <button onclick="window.print()">Print / Save PDF</button>
    </section>
    <section class="footer">
      This receipt is generated from BizXusAI payment records. For manual wallet/bank payments, the business owner remains responsible for verifying the actual transfer.
    </section>
  </main>
</body>
</html>"""


async def get_owner_payment_receipt_html(tenant_id: str, payment_record_id: str, user: dict) -> str:
    db = get_database()
    tenant_oid, tenant = await _ensure_payment_access(tenant_id, user)
    record_oid = parse_object_id(payment_record_id, "paymentRecordId")
    record = await db.payment_records.find_one({"_id": record_oid, "tenantId": tenant_oid})
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment record not found.")
    transaction = await db.transactions.find_one({"_id": record["transactionId"], "tenantId": tenant_oid})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found for this payment record.")
    return _build_payment_receipt_html(tenant, transaction, record)


async def get_customer_payment_receipt_html(order_id: str, payment_record_id: str, current_user: dict) -> str:
    db = get_database()
    transaction_oid = parse_object_id(order_id, "orderId")
    record_oid = parse_object_id(payment_record_id, "paymentRecordId")
    transaction = await db.transactions.find_one({"_id": transaction_oid, "customerUserId": current_user["_id"]})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    record = await db.payment_records.find_one({"_id": record_oid, "transactionId": transaction_oid, "tenantId": transaction["tenantId"]})
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment record not found for this order.")
    tenant = await db.tenants.find_one({"_id": transaction["tenantId"]}) or {}
    # The customer's copy of the receipt. `notes` carries the payment provider's raw
    # failure text, which is the same detail deliberately kept out of the HTTP error
    # body, so the record is stripped exactly as it is for every other customer view.
    # The owner's receipt above is unchanged and still shows everything.
    return _build_payment_receipt_html(tenant, transaction, _customer_safe_payment_record(record) or {})


async def _ensure_payment_access(tenant_id: str, user: dict) -> tuple[ObjectId, dict]:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "payments")
    return tenant_oid, tenant


async def get_payment_settings(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid, _ = await _ensure_payment_access(tenant_id, user)
    settings = await db.payment_settings.find_one({"tenantId": tenant_oid})
    if not settings:
        settings = _default_settings(tenant_oid, user.get("_id"))
        settings["_id"] = (await db.payment_settings.insert_one(settings)).inserted_id
    return serialize_payment_settings(settings)


async def update_payment_settings(tenant_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, _ = await _ensure_payment_access(tenant_id, user)
    default_method = _normalize_method(payload.defaultMethod)
    update = {
        "codEnabled": bool(payload.codEnabled),
        "manualEnabled": bool(payload.manualEnabled),
        "bankTransferEnabled": bool(payload.bankTransferEnabled),
        "jazzCashEnabled": bool(payload.jazzCashEnabled),
        "easyPaisaEnabled": bool(payload.easyPaisaEnabled),
        "stripeEnabled": bool(payload.stripeEnabled),
        "paymentsDemoMode": bool(payload.paymentsDemoMode),
        "requireOwnerApproval": bool(payload.requireOwnerApproval),
        "bankName": payload.bankName.strip(),
        "jazzCashNumber": payload.jazzCashNumber.strip(),
        "jazzCashAccountTitle": payload.jazzCashAccountTitle.strip(),
        "easyPaisaNumber": payload.easyPaisaNumber.strip(),
        "easyPaisaAccountTitle": payload.easyPaisaAccountTitle.strip(),
        "bankAccountTitle": payload.bankAccountTitle.strip(),
        "bankAccountNumber": payload.bankAccountNumber.strip(),
        "bankIban": payload.bankIban.strip(),
        "defaultMethod": default_method,
        "customerInstructions": payload.customerInstructions.strip(),
        "updatedAt": datetime.now(timezone.utc),
        "updatedBy": user.get("_id"),
    }
    if default_method == "jazzcash_mock" and not update["jazzCashEnabled"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enable JazzCash before setting it as default.")
    if default_method == "easypaisa_mock" and not update["easyPaisaEnabled"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enable EasyPaisa before setting it as default.")
    if default_method == "cod" and not update["codEnabled"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enable COD before setting it as default.")
    if default_method == "manual_bank" and not (update["manualEnabled"] or update["bankTransferEnabled"]):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enable manual payment before setting it as default.")
    if default_method == "stripe_test" and not update["stripeEnabled"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enable Stripe test card before setting it as default.")
    if update["stripeEnabled"] and not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe is not configured. Add STRIPE_SECRET_KEY to .env before enabling Stripe payments.")

    await db.payment_settings.update_one(
        {"tenantId": tenant_oid},
        {"$set": update, "$setOnInsert": {"tenantId": tenant_oid, "createdAt": datetime.now(timezone.utc), "createdBy": user.get("_id")}},
        upsert=True,
    )
    settings_doc = await db.payment_settings.find_one({"tenantId": tenant_oid})
    return serialize_payment_settings(settings_doc)


async def _get_transaction_or_404(tenant_oid: ObjectId, transaction_id: str) -> dict:
    db = get_database()
    transaction_oid = parse_object_id(transaction_id, "transactionId")
    transaction = await db.transactions.find_one({"_id": transaction_oid, "tenantId": tenant_oid})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    if transaction.get("transactionType") not in PAYABLE_TRANSACTION_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction type cannot accept payments.")
    if "not_applicable" in get_allowed_payment_statuses(transaction.get("transactionType", "order")) and transaction.get("paymentStatus") == "not_applicable":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payment is not applicable for this transaction.")
    return transaction


async def _calculate_payment_summary(tenant_oid: ObjectId, transaction: dict) -> dict[str, float]:
    db = get_database()
    transaction_id = transaction["_id"]
    records = await db.payment_records.find({"tenantId": tenant_oid, "transactionId": transaction_id}).to_list(length=None)
    paid = sum(float(row.get("amount", 0) or 0) for row in records if row.get("recordType") == "payment" and row.get("status") in {"paid", "completed"})
    pending = sum(float(row.get("amount", 0) or 0) for row in records if row.get("recordType") == "payment" and row.get("status") in {"pending_verification", "pending"})
    cod = sum(float(row.get("amount", 0) or 0) for row in records if row.get("recordType") == "payment" and row.get("status") == "cod")
    rejected = sum(float(row.get("amount", 0) or 0) for row in records if row.get("recordType") == "payment" and row.get("status") in {"rejected", "failed"})
    refunded = sum(float(row.get("amount", 0) or 0) for row in records if row.get("recordType") == "refund" or row.get("status") == "refunded")
    total = float(((transaction.get("pricing") or {}).get("total")) or 0)
    # Round every figure to the minor unit. Summing floats left balances like 1e-14,
    # which reported a fully paid order as partially paid and, on Stripe, produced a
    # one-paisa charge for the "remaining" amount.
    total = round(total, 2)
    paid = round(paid, 2)
    refunded = round(refunded, 2)
    net_paid = round(max(0.0, paid - refunded), 2)
    balance = round(max(0.0, total - net_paid), 2)
    if balance < 0.01:
        balance = 0.0
    return {
        "total": total,
        "paid": net_paid,
        "pending": round(pending, 2),
        "cod": round(cod, 2),
        "rejected": round(rejected, 2),
        "refunded": refunded,
        "balance": balance,
    }


def _payment_status_from_summary(transaction: dict, summary: dict[str, float]) -> str:
    if transaction.get("transactionType") == "quote_request" and transaction.get("status") != "approved":
        return transaction.get("paymentStatus", "awaiting_quote")
    if summary["refunded"] > 0 and summary["paid"] <= 0:
        return "refunded"
    if summary["paid"] >= summary["total"] and summary["total"] > 0:
        return "paid"
    if summary["paid"] > 0:
        return "partially_paid"
    if summary.get("pending", 0) > 0:
        return "pending_verification"
    if summary.get("cod", 0) > 0:
        return "cod"
    if summary.get("rejected", 0) > 0:
        return "rejected"
    return "unpaid"


async def write_reconciling_payment_record(
    tenant_oid: ObjectId,
    transaction: dict,
    *,
    amount: float,
    status_value: str,
    method: str,
    note: str,
    actor_user_id: ObjectId | None = None,
) -> dict | None:
    """Create the payment record implied by a status set outside the payment flow.

    Payment records are the single source of truth for what an order has been paid:
    `_calculate_payment_summary` recomputes from them and ignores any stored status. Two
    paths used to set `paymentStatus` with no record behind it — the owner's manual
    override and the historical-order import — so an order could read as paid while the
    summary said nothing had been received. That made an imported paid order collectable
    a second time, and made an owner-marked paid order flip back the moment a customer
    uploaded a proof.

    Writing the record here keeps those two paths honest without changing what the owner
    or the importer is allowed to express.
    """
    if status_value not in {"paid", "cod", "refunded"}:
        return None

    db = get_database()
    # Work out what is actually missing rather than trusting the caller: the order may
    # already have real payments against it, and writing the full total again would
    # double-count. `amount` is a ceiling, not an instruction.
    summary = await _calculate_payment_summary(tenant_oid, transaction)
    if status_value == "refunded":
        # There is nothing to refund beyond what was actually received - except on an
        # import, where the order arrives already refunded and has no prior payment
        # record to measure against. The caller's amount is the historical figure.
        outstanding = float(summary["paid"]) or round(float(amount or 0), 2)
    elif status_value == "cod":
        # COD sits in its own bucket which does NOT reduce `balance`, so using the
        # balance here meant an existing COD record was invisible and marking an order
        # cod a second time wrote another full-total row, doubling the dashboard figure.
        outstanding = max(0.0, float(summary["total"]) - float(summary["paid"]) - float(summary["cod"]))
    else:
        outstanding = float(summary["balance"])
    amount = round(min(float(amount or 0) or outstanding, outstanding), 2)
    if amount <= 0:
        return None
    now = datetime.now(timezone.utc)
    record = {
        "tenantId": tenant_oid,
        "transactionId": transaction["_id"],
        "transactionNumber": transaction.get("transactionNumber", ""),
        "customerSnapshot": transaction.get("customerSnapshot", {}),
        "recordType": "refund" if status_value == "refunded" else "payment",
        "amount": amount,
        "currency": (transaction.get("pricing") or {}).get("currency") or "PKR",
        "method": method,
        "methodLabel": _public_method_label(method),
        "status": status_value,
        "referenceNumber": "",
        "notes": note,
        "submittedBy": "business",
        "reconciling": True,
        "verification": {"requiresOwnerApproval": False, "verifiedByUserId": actor_user_id, "verifiedAt": now},
        "createdBy": actor_user_id,
        "createdAt": now,
        "updatedAt": now,
    }
    record["_id"] = (await db.payment_records.insert_one(record)).inserted_id
    return record


async def _sync_transaction_payment_status(tenant_oid: ObjectId, transaction: dict, actor_user_id: ObjectId | None, note: str) -> dict:
    """Recompute an order's payment status from its records.

    Every settlement path funnels through here, which is why the COD cleanup lives here
    too: putting it in the individual settle paths is how the gateway path got it and the
    Stripe path did not.
    """
    db = get_database()
    # Retire any COD placeholder first: the money arrived by another route, so the
    # "cash expected on delivery" row must stop counting or the same order shows up in
    # both the received and the COD totals on the owner's dashboard.
    summary = await _calculate_payment_summary(tenant_oid, transaction)
    # Only retire the COD expectation once the money actually covers the order. Firing on
    # any payment at all meant a 200 part-payment against a 1000 COD order closed the
    # placeholder and reported the order settled, so the outstanding 800 was never chased.
    # .get() throughout: this runs against summaries built by several callers, and a
    # missing key here must not take down a settlement.
    cod_outstanding = float(summary.get("cod", 0) or 0)
    total_due = float(summary.get("total", 0) or 0)
    if cod_outstanding > 0 and total_due > 0 and float(summary.get("paid", 0) or 0) >= total_due - 0.01:
        await close_cod_records_for_transaction(db, transaction["_id"])
        summary = await _calculate_payment_summary(tenant_oid, transaction)
    payment_status = _payment_status_from_summary(transaction, summary)
    now = datetime.now(timezone.utc)
    history = {
        "field": "paymentStatus",
        "from": transaction.get("paymentStatus"),
        "to": payment_status,
        "note": note,
        "changedAt": now,
        "changedByUserId": actor_user_id,
    }
    update = {"paymentSummary": summary, "paymentStatus": payment_status, "updatedAt": now}
    update_doc = {"$set": update}
    if payment_status != transaction.get("paymentStatus"):
        update_doc["$push"] = {"statusHistory": history}
    await db.transactions.update_one({"_id": transaction["_id"]}, update_doc)
    updated = await db.transactions.find_one({"_id": transaction["_id"]})

    # Every route that settles money lands here - gateway callback, Stripe webhook,
    # owner-recorded payment, cashier till - so this is the one place a payment
    # confirmation needs to be triggered from. Imported lazily to avoid a cycle:
    # order_message_service reaches back into this module's receipt helpers.
    if updated and payment_status != transaction.get("paymentStatus"):
        from app.services.order_message_service import notify_payment_confirmed

        await notify_payment_confirmed(updated)
    return updated


async def submit_customer_payment_proof(
    order_id: str,
    amount: float,
    method: str | None,
    reference_number: str,
    notes: str,
    current_user: dict,
    proof_file=None,
) -> dict:
    db = get_database()
    transaction_oid = parse_object_id(order_id, "orderId")
    transaction = await db.transactions.find_one({"_id": transaction_oid, "customerUserId": current_user["_id"]})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    if transaction.get("transactionType") not in PAYABLE_TRANSACTION_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction cannot accept payment proof.")

    tenant_oid = transaction["tenantId"]
    tenant = await db.tenants.find_one({"_id": tenant_oid}) or {}
    # Validate against the tenant's live settings, never the snapshot stored on the
    # order. The snapshot froze at order time, so a method the owner enabled afterwards
    # was refused for existing orders and one they disabled was still accepted.
    payment_options = await get_customer_payment_options_for_tenant(tenant_oid)
    selected_method = _normalize_method(method or (transaction.get("paymentPreference") or {}).get("method") or payment_options.get("defaultMethod"))
    if selected_method == "cod":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="COD does not require payment proof. The business will collect cash directly.")
    normalize_customer_payment_preference(selected_method, payment_options)

    # Defence in depth: the route's own gt=0 is the first check, but this service is
    # also reachable from other callers.
    amount = round(float(amount), 2)
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payment amount must be greater than zero.")
    current_summary = await _calculate_payment_summary(tenant_oid, transaction)
    if amount > current_summary["balance"] + 0.01:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payment proof amount cannot exceed the remaining balance.")
    if not reference_number.strip() and not proof_file:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a payment reference or upload a proof screenshot.")

    proof = await store_payment_proof_image(str(tenant_oid), str(transaction["_id"]), proof_file) if proof_file else {}
    now = datetime.now(timezone.utc)
    record = {
        "tenantId": tenant_oid,
        "transactionId": transaction["_id"],
        "transactionNumber": transaction.get("transactionNumber", ""),
        "customerSnapshot": transaction.get("customerSnapshot", {}),
        "recordType": "payment",
        "amount": float(amount),
        "currency": (transaction.get("pricing") or {}).get("currency") or ((transaction.get("items") or [{}])[0].get("currency")) or "PKR",
        "method": selected_method,
        "methodLabel": _public_method_label(selected_method),
        "status": "pending_verification",
        "referenceNumber": reference_number.strip(),
        "screenshotUrl": proof.get("url", ""),
        "notes": notes.strip(),
        "submittedBy": "customer",
        "verification": {
            "requiresOwnerApproval": True,
            "submittedByCustomerUserId": current_user["_id"],
            "submittedAt": now,
            "verifiedByUserId": None,
            "verifiedAt": None,
            "rejectedByUserId": None,
            "rejectedAt": None,
        },
        "createdBy": current_user["_id"],
        "createdAt": now,
        "updatedAt": now,
    }
    record["_id"] = (await db.payment_records.insert_one(record)).inserted_id
    updated_transaction = await _sync_transaction_payment_status(tenant_oid, transaction, current_user.get("_id"), f"Customer submitted payment proof through {selected_method}.")

    await create_business_notification(
        tenant_oid,
        "payment_proof_submitted",
        f"Payment proof submitted for {transaction.get('transactionNumber', 'transaction')}",
        f"{transaction.get('customerSnapshot', {}).get('name') or 'A customer'} submitted {float(amount):g} proof through {_public_method_label(selected_method)}.",
        priority="high",
        metadata={"transactionId": str(transaction["_id"]), "paymentRecordId": str(record["_id"]), "tenantSlug": tenant.get("slug", "")},
    )
    await create_customer_notification(
        current_user["_id"],
        tenant_oid,
        "payment_submitted",
        f"Payment proof submitted for {transaction.get('transactionNumber', 'order')}",
        "Your payment proof was sent to the business owner for verification.",
        {"transactionId": str(transaction["_id"]), "paymentRecordId": str(record["_id"]), "tenantSlug": tenant.get("slug", "")},
    )
    return {"payment": serialize_document(record), "transaction": serialize_document(updated_transaction)}


async def decide_payment_record(tenant_id: str, payment_record_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _ensure_payment_access(tenant_id, user)
    record_oid = parse_object_id(payment_record_id, "paymentRecordId")
    record = await db.payment_records.find_one({"_id": record_oid, "tenantId": tenant_oid, "recordType": "payment"})
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment record not found.")
    if record.get("status") != "pending_verification":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only pending payment proofs can be approved or rejected.")

    decision = str(payload.decision or "").strip().lower()
    if decision not in {"approve", "approved", "paid", "reject", "rejected"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Decision must be approve or reject.")
    next_status = "paid" if decision in {"approve", "approved", "paid"} else "rejected"
    transaction = await _get_transaction_or_404(tenant_oid, str(record["transactionId"]))
    if next_status == "paid":
        current_summary = await _calculate_payment_summary(tenant_oid, transaction)
        if float(record.get("amount", 0) or 0) > current_summary["balance"] + 0.01:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payment amount cannot exceed the remaining balance.")

    now = datetime.now(timezone.utc)
    verification_update = {
        **(record.get("verification") or {}),
        "requiresOwnerApproval": False,
        "decisionNotes": payload.notes.strip(),
    }
    if next_status == "paid":
        verification_update.update({"verifiedByUserId": user.get("_id"), "verifiedAt": now})
    else:
        verification_update.update({"rejectedByUserId": user.get("_id"), "rejectedAt": now})

    # Filtered on the state the balance check above was made against, so two concurrent
    # approvals of two full-total proofs cannot both credit the order. Every other path
    # that writes "paid" claims the record this way; this one was check-then-act.
    decided = await db.payment_records.update_one(
        {"_id": record_oid, "status": "pending_verification"},
        {
            "$set": {
                "status": next_status,
                "verification": verification_update,
                "updatedAt": now,
                "updatedBy": user.get("_id"),
                "ownerDecisionNotes": payload.notes.strip(),
            }
        },
    )
    if not decided.modified_count:
        # Another approval reached it first; crediting again would double the payment.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This payment proof has already been decided. Reload to see the current state.",
        )
    updated_record = await db.payment_records.find_one({"_id": record_oid})
    updated_transaction = await _sync_transaction_payment_status(tenant_oid, transaction, user.get("_id"), f"Payment proof {next_status}.")

    await create_business_notification(
        tenant_oid,
        "payment_proof_decided",
        f"Payment proof {next_status} for {transaction.get('transactionNumber', 'transaction')}",
        f"{float(record.get('amount', 0) or 0):g} through {record.get('methodLabel') or record.get('method')} was {next_status}.",
        priority="medium",
        metadata={"transactionId": str(transaction["_id"]), "paymentRecordId": str(record_oid), "tenantSlug": tenant.get("slug", "")},
    )
    if updated_transaction.get("customerUserId"):
        title = "Payment approved" if next_status == "paid" else "Payment rejected"
        body = (
            f"Your payment for {updated_transaction.get('transactionNumber', 'order')} was approved."
            if next_status == "paid"
            else f"Your payment proof for {updated_transaction.get('transactionNumber', 'order')} was rejected. Please submit a correct reference or contact the business."
        )
        await create_customer_notification(
            updated_transaction["customerUserId"],
            tenant_oid,
            "payment_decision",
            title,
            body,
            {"transactionId": str(updated_transaction["_id"]), "paymentRecordId": str(record_oid), "tenantSlug": tenant.get("slug", "")},
        )

    return {"payment": serialize_document(updated_record), "transaction": serialize_document(updated_transaction)}


async def list_payment_overview(tenant_id: str, user: dict, page: int = 1, limit: int = 20) -> dict:
    db = get_database()
    tenant_oid, _ = await _ensure_payment_access(tenant_id, user)
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    settings = await get_payment_settings(tenant_id, user)

    payment_query = {"tenantId": tenant_oid}
    total_records = await db.payment_records.count_documents(payment_query)
    records_cursor = db.payment_records.find(payment_query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    records = [payment_record_view(row) async for row in records_cursor]

    outstanding_cursor = db.transactions.find(
        {
            "tenantId": tenant_oid,
            "transactionType": {"$in": ["order", "booking_request"]},
            "status": {"$ne": "cancelled"},
            "paymentStatus": {"$in": ["unpaid", "partially_paid", "pending_verification", "rejected"]},
        }
    ).sort("createdAt", -1).limit(25)
    outstanding = []
    async for row in outstanding_cursor:
        serialized = serialize_document(row)
        serialized["paymentProofSummary"] = await summarize_payment_records_for_transaction(row)
        outstanding.append(serialized)

    completed_records = await db.payment_records.find({"tenantId": tenant_oid, "recordType": "payment", "status": {"$in": ["paid", "completed"]}}).to_list(length=None)
    pending_records = await db.payment_records.find({"tenantId": tenant_oid, "recordType": "payment", "status": {"$in": ["pending_verification", "pending"]}}).to_list(length=None)
    cod_records = await db.payment_records.find({"tenantId": tenant_oid, "recordType": "payment", "status": "cod"}).to_list(length=None)
    rejected_records = await db.payment_records.find({"tenantId": tenant_oid, "recordType": "payment", "status": {"$in": ["rejected", "failed"]}}).to_list(length=None)
    refunded_records = await db.payment_records.find({"tenantId": tenant_oid, "$or": [{"recordType": "refund"}, {"status": "refunded"}]}).to_list(length=None)
    stripe_paid_records = await db.payment_records.find({"tenantId": tenant_oid, "recordType": "payment", "provider": "stripe", "status": {"$in": ["paid", "completed"]}}).to_list(length=None)
    stripe_pending_records = await db.payment_records.find({"tenantId": tenant_oid, "recordType": "payment", "provider": "stripe", "status": {"$in": ["pending_verification", "pending"]}}).to_list(length=None)
    stripe_failed_records = await db.payment_records.find({"tenantId": tenant_oid, "recordType": "payment", "provider": "stripe", "status": {"$in": ["failed", "rejected"]}}).to_list(length=None)
    stripe_events = await db.stripe_webhook_events.find({"tenantId": tenant_oid}).sort("createdAt", -1).limit(10).to_list(length=10)
    summary = {
        "received": sum(float(row.get("amount", 0) or 0) for row in completed_records),
        "pendingVerification": sum(float(row.get("amount", 0) or 0) for row in pending_records),
        "cod": sum(float(row.get("amount", 0) or 0) for row in cod_records),
        "rejected": sum(float(row.get("amount", 0) or 0) for row in rejected_records),
        "refunded": sum(float(row.get("amount", 0) or 0) for row in refunded_records),
        "outstandingTransactions": len(outstanding),
        "totalRecords": total_records,
        "stripeReceived": sum(float(row.get("amount", 0) or 0) for row in stripe_paid_records),
        "stripePending": sum(float(row.get("amount", 0) or 0) for row in stripe_pending_records),
        "stripeFailedCount": len(stripe_failed_records),
        "stripeWebhookEvents": len(stripe_events),
    }
    summary["netReceived"] = max(0.0, summary["received"] - summary["refunded"])

    return {
        "settings": settings,
        "records": records,
        "outstandingTransactions": outstanding,
        "stripeWebhookEvents": [serialize_document(event) for event in stripe_events],
        "summary": summary,
        "pagination": {"page": page, "limit": limit, "total": total_records, "totalPages": (total_records + limit - 1) // limit},
    }


async def record_transaction_payment(tenant_id: str, transaction_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _ensure_payment_access(tenant_id, user)
    transaction = await _get_transaction_or_404(tenant_oid, transaction_id)
    method = _normalize_method(payload.method)
    record_status = _normalize_record_status(payload.status)
    settings = await get_payment_settings(tenant_id, user)
    if method == "cod" and not settings.get("codEnabled"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="COD is disabled for this business.")
    if method == "manual_bank" and not (settings.get("manualEnabled") or settings.get("bankTransferEnabled")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Manual payments are disabled for this business.")
    if method == "jazzcash_mock" and not settings.get("jazzCashEnabled"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="JazzCash is disabled for this business.")
    if method == "easypaisa_mock" and not settings.get("easyPaisaEnabled"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="EasyPaisa is disabled for this business.")
    if method == "stripe_test" and not settings.get("stripeEnabled"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe test card is disabled for this business.")
    if method == "cod" and record_status == "paid":
        record_status = "cod"

    current_summary = await _calculate_payment_summary(tenant_oid, transaction)
    # COD sits in its own summary bucket that does NOT reduce `balance`, so comparing a
    # COD entry against the balance alone made an existing COD record invisible and let
    # the owner record the full total twice.
    allowance = current_summary["balance"]
    if record_status == "cod":
        allowance = max(0.0, float(current_summary["total"]) - float(current_summary["paid"]) - float(current_summary["cod"]))
    if record_status in {"paid", "cod"} and payload.amount > allowance + 0.01:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Payment amount cannot exceed the remaining balance.")

    now = datetime.now(timezone.utc)
    record = {
        "tenantId": tenant_oid,
        "transactionId": transaction["_id"],
        "transactionNumber": transaction.get("transactionNumber", ""),
        "customerSnapshot": transaction.get("customerSnapshot", {}),
        "recordType": "payment",
        "amount": float(payload.amount),
        "currency": (transaction.get("pricing") or {}).get("currency") or ((transaction.get("items") or [{}])[0].get("currency")) or "PKR",
        "method": method,
        "methodLabel": _public_method_label(method),
        "status": record_status,
        "referenceNumber": payload.referenceNumber.strip(),
        "screenshotUrl": getattr(payload, "screenshotUrl", "").strip(),
        "notes": payload.notes.strip(),
        "verification": {
            "requiresOwnerApproval": bool(settings.get("requireOwnerApproval", True)) and record_status == "pending_verification",
            "verifiedByUserId": user.get("_id") if record_status in {"paid", "cod"} else None,
            "verifiedAt": now if record_status in {"paid", "cod"} else None,
            "rejectedByUserId": user.get("_id") if record_status == "rejected" else None,
            "rejectedAt": now if record_status == "rejected" else None,
        },
        "createdBy": user.get("_id"),
        "createdAt": now,
        "updatedAt": now,
    }
    record["_id"] = (await db.payment_records.insert_one(record)).inserted_id
    updated_transaction = await _sync_transaction_payment_status(tenant_oid, transaction, user.get("_id"), f"Payment recorded through {method}.")

    await create_business_notification(
        tenant_oid,
        "payment_recorded",
        f"Payment recorded for {transaction.get('transactionNumber', 'transaction')}",
        f"{float(payload.amount):g} recorded through {method} for {transaction.get('transactionNumber', 'transaction')}.",
        priority="medium",
        metadata={"transactionId": str(transaction["_id"]), "paymentRecordId": str(record["_id"]), "tenantSlug": tenant.get("slug", "")},
    )
    if updated_transaction.get("customerUserId") and record_status in {"paid", "cod"}:
        await create_customer_notification(
            updated_transaction["customerUserId"],
            tenant_oid,
            "payment_updated",
            f"Payment recorded for {updated_transaction.get('transactionNumber', 'order')}",
            f"Your payment of {float(payload.amount):g} was recorded by {tenant.get('name', 'the business')}.",
            {"transactionId": str(updated_transaction["_id"]), "tenantSlug": tenant.get("slug", "")},
        )

    return {"payment": serialize_document(record), "transaction": serialize_document(updated_transaction)}


async def refund_transaction_payment(tenant_id: str, transaction_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid, tenant = await _ensure_payment_access(tenant_id, user)
    transaction = await _get_transaction_or_404(tenant_oid, transaction_id)
    method = _normalize_method(payload.method)
    current_summary = await _calculate_payment_summary(tenant_oid, transaction)
    if payload.amount > current_summary["paid"] + 0.01:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Refund amount cannot exceed paid amount.")

    now = datetime.now(timezone.utc)
    record = {
        "tenantId": tenant_oid,
        "transactionId": transaction["_id"],
        "transactionNumber": transaction.get("transactionNumber", ""),
        "customerSnapshot": transaction.get("customerSnapshot", {}),
        "recordType": "refund",
        "amount": float(payload.amount),
        "currency": (transaction.get("pricing") or {}).get("currency") or ((transaction.get("items") or [{}])[0].get("currency")) or "PKR",
        "method": method,
        "methodLabel": _public_method_label(method),
        "status": "refunded",
        "referenceNumber": payload.referenceNumber.strip(),
        "notes": payload.notes.strip(),
        "verification": {
            "verifiedByUserId": user.get("_id"),
            "verifiedAt": now,
        },
        "createdBy": user.get("_id"),
        "createdAt": now,
        "updatedAt": now,
    }
    record["_id"] = (await db.payment_records.insert_one(record)).inserted_id
    updated_transaction = await _sync_transaction_payment_status(tenant_oid, transaction, user.get("_id"), f"Refund recorded through {method}.")
    if updated_transaction.get("paymentStatus") == "refunded":
        updated_transaction = await restore_transaction_stock(updated_transaction, user.get("_id"))
    await create_business_notification(
        tenant_oid,
        "payment_refunded",
        f"Refund recorded for {transaction.get('transactionNumber', 'transaction')}",
        f"{float(payload.amount):g} refunded through {method} for {transaction.get('transactionNumber', 'transaction')}.",
        priority="medium",
        metadata={"transactionId": str(transaction["_id"]), "paymentRecordId": str(record["_id"]), "tenantSlug": tenant.get("slug", "")},
    )
    return {"payment": serialize_document(record), "transaction": serialize_document(updated_transaction)}


def _stripe_amount_to_minor_units(amount: float) -> int:
    return max(1, int(round(float(amount or 0) * 100)))


def _stripe_return_url(path_template: str, order_id: str, override_url: str = "") -> str:
    if override_url:
        return override_url
    path = path_template.replace("{orderId}", order_id)
    return urljoin(settings.frontend_base_url.rstrip("/") + "/", path.lstrip("/"))


def _stripe_success_url(path_template: str, order_id: str, override_url: str = "") -> str:
    success_url = _stripe_return_url(path_template, order_id, override_url)
    if "session_id=" in success_url:
        return success_url
    separator = "&" if "?" in success_url else "?"
    return f"{success_url}{separator}session_id={{CHECKOUT_SESSION_ID}}"


STRIPE_SIGNATURE_TOLERANCE_SECONDS = 300


def _verify_stripe_signature(payload: bytes, signature_header: str) -> bool:
    """Verify Stripe's `Stripe-Signature` header, failing closed.

    An unverified webhook can mark any order paid, so a missing secret is treated as a
    rejection rather than a reason to skip the check.
    """
    if not settings.stripe_webhook_secret:
        logger.error("Rejecting Stripe webhook: STRIPE_WEBHOOK_SECRET is not configured.")
        return False

    pieces: dict[str, list[str]] = {}
    for part in signature_header.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            pieces.setdefault(key, []).append(value.strip())
    timestamp = pieces.get("t", [""])[0]
    signatures = pieces.get("v1", [])
    if not timestamp or not signatures:
        return False

    # Reject stale headers so a captured webhook cannot be replayed indefinitely.
    try:
        age_seconds = abs(datetime.now(timezone.utc).timestamp() - int(timestamp))
    except (TypeError, ValueError):
        return False
    if age_seconds > STRIPE_SIGNATURE_TOLERANCE_SECONDS:
        logger.warning("Rejecting Stripe webhook: signature timestamp is %.0fs old.", age_seconds)
        return False

    signed_payload = b"%s.%s" % (timestamp.encode("utf-8"), payload)
    expected = hmac.new(settings.stripe_webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, signature) for signature in signatures)


# Stripe Checkout Sessions expire 24 hours after creation. Reusing one past that point
# hands the customer a dead link with no way to get a new one.
STRIPE_SESSION_MAX_AGE_SECONDS = 24 * 60 * 60


def _stripe_currency_for(transaction: dict) -> str:
    """The currency a Stripe charge for this order must be made in.

    The order's own currency is authoritative. Charging the numeric balance in whatever
    STRIPE_CURRENCY happened to be set to meant a tenant trading in one currency had
    their balance charged as another, and the payment summary then added up amounts in
    two different currencies as if they were the same.

    A mismatch is refused rather than silently converted: this codebase has no exchange
    rates, so there is no correct number to send.
    """
    order_currency = str((transaction.get("pricing") or {}).get("currency") or "").strip().upper()
    configured = str(settings.stripe_currency or "").strip().upper()
    if not order_currency:
        return configured
    if configured and order_currency != configured:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This order is priced in {order_currency}, but Stripe is configured for {configured}. "
                "Use another payment method, or set STRIPE_CURRENCY to match the business currency."
            ),
        )
    return order_currency


async def close_cod_records_for_transaction(db, transaction_id: ObjectId, *, keep_id: ObjectId | None = None) -> None:
    """Retire the COD placeholders once the money has actually arrived.

    A COD record means "cash is expected on delivery". Nothing ever retired it when the
    cash was collected, so `_calculate_payment_summary` kept counting the same order in
    both the `cod` bucket and the `paid` bucket, and the owner's dashboard showed the
    money twice.
    """
    query = {"transactionId": transaction_id, "recordType": "payment", "status": "cod"}
    if keep_id is not None:
        query["_id"] = {"$ne": keep_id}
    await db.payment_records.update_many(
        query,
        # "cancelled" belongs to no bucket in _calculate_payment_summary. "completed" was
        # the wrong terminal status: it is counted as PAID, so retiring the placeholder
        # that way moved the double count rather than removing it.
        {"$set": {"status": "cancelled", "notes": "Superseded: the money arrived by another route.", "updatedAt": datetime.now(timezone.utc)}},
    )


async def _supersede_pending_attempts(db, transaction_id: ObjectId, provider: str, *, keep_id: ObjectId | None = None) -> None:
    """Fail earlier unfinished attempts for this provider on this order.

    Every click of "pay" used to insert another pending record for the full balance,
    with no attempt to close the previous one. Those piled up: they kept the order
    showing as awaiting review, inflated the owner's dashboard, and two OTP attempts
    started back to back could each be verified, crediting the order twice.
    """
    # Scoped to the ORDER, not to one provider. Scoping by provider let a customer open
    # a JazzCash attempt and an Easypaisa attempt back to back and settle both for the
    # full total. `provider` is kept only for the note.
    query = {
        "transactionId": transaction_id,
        "recordType": "payment",
        "provider": {"$nin": ["", None]},
        "status": "pending_verification",
    }
    if keep_id is not None:
        query["_id"] = {"$ne": keep_id}
    await db.payment_records.update_many(
        query,
        {"$set": {"status": "failed", "notes": "Superseded by a newer payment attempt.", "updatedAt": datetime.now(timezone.utc)}},
    )


async def _active_stripe_session_for_transaction(db, transaction_id: ObjectId, balance: float | None = None) -> dict[str, Any] | None:
    record = await db.payment_records.find_one(
        {
            "transactionId": transaction_id,
            "recordType": "payment",
            "method": "stripe_test",
            "provider": "stripe",
            "status": "pending_verification",
            "providerSessionId": {"$ne": ""},
        },
        sort=[("createdAt", -1)],
    )
    if not record or not record.get("providerSessionUrl"):
        return None

    created_at = record.get("createdAt")
    if isinstance(created_at, datetime):
        age = (datetime.now(timezone.utc) - created_at.replace(tzinfo=created_at.tzinfo or timezone.utc)).total_seconds()
        if age > STRIPE_SESSION_MAX_AGE_SECONDS:
            await db.payment_records.update_one(
                {"_id": record["_id"], "status": "pending_verification"},
                {"$set": {"status": "failed", "notes": "Stripe checkout session expired.", "updatedAt": datetime.now(timezone.utc)}},
            )
            return None

    # A partial payment since this attempt started makes the stored amount wrong, so the
    # customer would be charged the old balance.
    if balance is not None and abs(float(record.get("amount", 0) or 0) - float(balance)) > 0.009:
        await db.payment_records.update_one(
            {"_id": record["_id"], "status": "pending_verification"},
            {"$set": {"status": "failed", "notes": "Order balance changed; a new checkout is needed.", "updatedAt": datetime.now(timezone.utc)}},
        )
        return None

    return {
        "checkoutUrl": record.get("providerSessionUrl", ""),
        "sessionId": record.get("providerSessionId", ""),
        "paymentRecordId": str(record["_id"]),
        "reused": True,
    }


async def _retrieve_stripe_checkout_session(session_id: str) -> dict[str, Any]:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe is not configured. Add STRIPE_SECRET_KEY to .env.")
    if not session_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe session id is missing.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
                auth=(settings.stripe_secret_key, ""),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to contact Stripe. Please try again.") from exc
    if response.status_code >= 400:
        try:
            stripe_error = response.json().get("error", {}).get("message")
        except Exception:
            stripe_error = ""
        # Stripe's own message can name the account, the API version and the exact
        # parameter at fault. The owner gets it in the log; the caller gets a sentence.
        logger.warning("Stripe session retrieval failed: %s", stripe_error)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to retrieve Stripe checkout session.")
    return response.json()


def _ensure_session_metadata(session: dict[str, Any], transaction: dict, record: dict | None = None) -> dict[str, Any]:
    metadata = dict(session.get("metadata") or {})
    metadata.setdefault("tenantId", str(transaction.get("tenantId", "")))
    metadata.setdefault("transactionId", str(transaction.get("_id", "")))
    if record:
        metadata.setdefault("paymentRecordId", str(record.get("_id", "")))
    session["metadata"] = metadata
    session.setdefault("client_reference_id", str(transaction.get("_id", "")))
    return session


async def create_customer_stripe_checkout_session(order_id: str, current_user: dict, success_url: str = "", cancel_url: str = "") -> dict[str, Any]:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe is not configured. Add STRIPE_SECRET_KEY to .env.")

    db = get_database()
    transaction_oid = parse_object_id(order_id, "orderId")
    transaction = await db.transactions.find_one({"_id": transaction_oid, "customerUserId": current_user["_id"]})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    if transaction.get("transactionType") not in PAYABLE_TRANSACTION_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction cannot be paid online.")

    tenant_oid = transaction["tenantId"]
    # Validate against the tenant's live settings, never the snapshot stored on the
    # order. The snapshot froze at order time, so a method the owner enabled afterwards
    # was refused for existing orders and one they disabled was still accepted.
    payment_options = await get_customer_payment_options_for_tenant(tenant_oid)
    normalize_customer_payment_preference("stripe_test", payment_options)
    current_summary = await _calculate_payment_summary(tenant_oid, transaction)
    balance = current_summary["balance"]
    if balance <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction has no remaining balance.")
    active_session = await _active_stripe_session_for_transaction(db, transaction["_id"], balance)
    if active_session:
        return {**active_session, "transaction": serialize_document(transaction)}

    now = datetime.now(timezone.utc)
    record = {
        "tenantId": tenant_oid,
        "transactionId": transaction["_id"],
        "transactionNumber": transaction.get("transactionNumber", ""),
        "customerSnapshot": transaction.get("customerSnapshot", {}),
        "recordType": "payment",
        "amount": float(balance),
        "currency": _stripe_currency_for(transaction),
        "method": "stripe_test",
        "methodLabel": _public_method_label("stripe_test"),
        "status": "pending_verification",
        "referenceNumber": "",
        "notes": "Stripe Checkout session created.",
        "submittedBy": "customer",
        "provider": "stripe",
        "providerMode": "test",
        "providerSessionId": "",
        "providerPaymentIntentId": "",
        "createdBy": current_user["_id"],
        "createdAt": now,
        "updatedAt": now,
    }
    # Close the previous unfinished attempt, as the gateway and OTP paths do. These two
    # Stripe creation sites were the only ones that never did, so a customer could hold a
    # live Stripe session and a live wallet attempt against the same order at once.
    await _supersede_pending_attempts(db, transaction["_id"], "stripe")
    record["_id"] = (await db.payment_records.insert_one(record)).inserted_id

    stripe_provider = providers.StripeProvider()
    context = PaymentContext(
        provider="stripe",
        reference=str(record["_id"]),
        amount=float(balance),
        currency=_stripe_currency_for(transaction),
        order_id=str(transaction["_id"]),
        order_number=transaction.get("transactionNumber", ""),
        tenant_id=str(tenant_oid),
        customer_email=(transaction.get("customerSnapshot") or {}).get("email") or current_user.get("email", ""),
        success_url=_stripe_success_url(settings.stripe_success_path, str(transaction["_id"]), success_url),
        cancel_url=_stripe_return_url(settings.stripe_cancel_path, str(transaction["_id"]), cancel_url),
    )
    try:
        initiation = await stripe_provider.initiate(context)
    except PaymentProviderError as exc:
        await db.payment_records.update_one(
            {"_id": record["_id"]},
            {"$set": {"status": "failed", "notes": str(exc), "updatedAt": datetime.now(timezone.utc)}},
        )
        logger.warning("Payment provider error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider could not be reached just now. Please try again in a moment.",
        ) from exc

    session = {"id": initiation.provider_session_id, "url": initiation.provider_session_url}
    await db.payment_records.update_one(
        {"_id": record["_id"]},
        {"$set": {"providerSessionId": session["id"], "providerSessionUrl": session["url"], "referenceNumber": session["id"], "notes": initiation.notes, "updatedAt": datetime.now(timezone.utc)}},
    )
    updated_transaction = await _sync_transaction_payment_status(tenant_oid, transaction, current_user.get("_id"), "Stripe Checkout session created.")
    await create_business_notification(
        tenant_oid,
        "stripe_checkout_created",
        f"Stripe checkout started for {transaction.get('transactionNumber', 'transaction')}",
        f"Customer opened Stripe Checkout for {float(balance):g}.",
        priority="medium",
        metadata={"transactionId": str(transaction["_id"]), "paymentRecordId": str(record["_id"]), "stripeSessionId": session.get("id", "")},
    )
    return {"checkoutUrl": session.get("url", ""), "sessionId": session.get("id", ""), "paymentRecordId": str(record["_id"]), "transaction": serialize_document(updated_transaction)}


async def create_public_stripe_checkout_session(slug: str, transaction_id: str, success_url: str = "", cancel_url: str = "") -> dict[str, Any]:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Stripe is not configured. Add STRIPE_SECRET_KEY to .env.")

    db = get_database()
    tenant = await db.tenants.find_one({"slug": slug, "status": "active", "websiteStatus": "published"})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published business not found.")
    transaction_oid = parse_object_id(transaction_id, "transactionId")
    transaction = await db.transactions.find_one({"_id": transaction_oid, "tenantId": tenant["_id"], "source": {"$in": ["public_website", "public_chat"]}})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public transaction not found.")
    # See the note above: eligibility comes from live settings, not the order snapshot.
    payment_options = await get_customer_payment_options_for_tenant(tenant["_id"])
    normalize_customer_payment_preference("stripe_test", payment_options)
    current_summary = await _calculate_payment_summary(tenant["_id"], transaction)
    balance = current_summary["balance"]
    if balance <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction has no remaining balance.")
    active_session = await _active_stripe_session_for_transaction(db, transaction["_id"], balance)
    if active_session:
        return {**active_session, "transaction": serialize_document(transaction)}

    now = datetime.now(timezone.utc)
    record = {
        "tenantId": tenant["_id"],
        "transactionId": transaction["_id"],
        "transactionNumber": transaction.get("transactionNumber", ""),
        "customerSnapshot": transaction.get("customerSnapshot", {}),
        "recordType": "payment",
        "amount": float(balance),
        "currency": _stripe_currency_for(transaction),
        "method": "stripe_test",
        "methodLabel": _public_method_label("stripe_test"),
        "status": "pending_verification",
        "referenceNumber": "",
        "notes": "Public Stripe Checkout session created.",
        "submittedBy": "public_customer",
        "provider": "stripe",
        "providerMode": "test",
        "providerSessionId": "",
        "providerPaymentIntentId": "",
        "createdAt": now,
        "updatedAt": now,
    }
    # Close the previous unfinished attempt, as the gateway and OTP paths do. These two
    # Stripe creation sites were the only ones that never did, so a customer could hold a
    # live Stripe session and a live wallet attempt against the same order at once.
    await _supersede_pending_attempts(db, transaction["_id"], "stripe")
    record["_id"] = (await db.payment_records.insert_one(record)).inserted_id
    public_success = success_url or urljoin(settings.frontend_base_url.rstrip("/") + "/", f"businesses/{slug}?payment=stripe_success&order={transaction['_id']}&session_id={{CHECKOUT_SESSION_ID}}")
    if "session_id=" not in public_success:
        public_success = f"{public_success}{'&' if '?' in public_success else '?'}session_id={{CHECKOUT_SESSION_ID}}"
    public_cancel = cancel_url or urljoin(settings.frontend_base_url.rstrip("/") + "/", f"businesses/{slug}?payment=stripe_cancelled&order={transaction['_id']}")
    payload = {
        "mode": "payment",
        "success_url": public_success,
        "cancel_url": public_cancel,
        "client_reference_id": str(transaction["_id"]),
        "customer_email": (transaction.get("customerSnapshot") or {}).get("email") or "",
        "metadata[tenantId]": str(tenant["_id"]),
        "metadata[transactionId]": str(transaction["_id"]),
        "metadata[paymentRecordId]": str(record["_id"]),
        "payment_intent_data[metadata][tenantId]": str(tenant["_id"]),
        "payment_intent_data[metadata][transactionId]": str(transaction["_id"]),
        "payment_intent_data[metadata][paymentRecordId]": str(record["_id"]),
        "line_items[0][price_data][currency]": _stripe_currency_for(transaction).lower(),
        "line_items[0][price_data][product_data][name]": f"{transaction.get('transactionNumber', 'BizXusAI public order')} payment",
        "line_items[0][price_data][unit_amount]": str(_stripe_amount_to_minor_units(balance)),
        "line_items[0][quantity]": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=payload,
                auth=(settings.stripe_secret_key, ""),
                headers={"Idempotency-Key": f"bizxusai-public-checkout-{record['_id']}"},
            )
    except httpx.HTTPError as exc:
        await db.payment_records.update_one({"_id": record["_id"]}, {"$set": {"status": "failed", "notes": f"Stripe request failed: {exc.__class__.__name__}", "updatedAt": datetime.now(timezone.utc)}})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to create Stripe checkout session. Please try again.") from exc
    if response.status_code >= 400:
        try:
            stripe_error = response.json().get("error", {}).get("message")
        except Exception:
            stripe_error = ""
        await db.payment_records.update_one({"_id": record["_id"]}, {"$set": {"status": "failed", "notes": stripe_error or "Stripe checkout session failed.", "updatedAt": datetime.now(timezone.utc)}})
        # This one is reachable unauthenticated from the public checkout, so it must not
        # echo Stripe's message. It is kept on the payment record for the owner.
        logger.warning("Stripe checkout creation failed: %s", stripe_error)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to create Stripe checkout session.")
    session = response.json()
    await db.payment_records.update_one(
        {"_id": record["_id"]},
        {"$set": {"providerSessionId": session.get("id", ""), "providerSessionUrl": session.get("url", ""), "referenceNumber": session.get("id", ""), "notes": "Stripe Checkout session is waiting for public customer payment.", "updatedAt": datetime.now(timezone.utc)}},
    )
    updated_transaction = await _sync_transaction_payment_status(tenant["_id"], transaction, None, "Public Stripe Checkout session created.")
    await create_business_notification(
        tenant["_id"],
        "stripe_checkout_created",
        f"Stripe checkout started for {transaction.get('transactionNumber', 'transaction')}",
        f"Public customer opened Stripe Checkout for {float(balance):g}.",
        priority="medium",
        metadata={"transactionId": str(transaction["_id"]), "paymentRecordId": str(record["_id"]), "stripeSessionId": session.get("id", "")},
    )
    return {"checkoutUrl": session.get("url", ""), "sessionId": session.get("id", ""), "paymentRecordId": str(record["_id"]), "transaction": serialize_document(updated_transaction)}


def stripe_session_is_paid(session: dict[str, Any] | None) -> bool:
    """Whether a Checkout Session really represents money received.

    `status == "complete"` only means the customer finished the flow. For a
    delayed-notification method Stripe sends `checkout.session.completed` with
    `payment_status: "unpaid"`, and the funds may never arrive. Only `payment_status`
    settles an order; `async_payment_succeeded` delivers the later confirmation.
    """
    return str((session or {}).get("payment_status") or "") in {"paid", "no_payment_required"}


async def mark_stripe_checkout_completed(session: dict[str, Any]) -> dict[str, Any]:
    db = get_database()
    if not stripe_session_is_paid(session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Stripe session has not been paid yet.",
        )
    metadata = session.get("metadata") or {}
    transaction_oid = parse_object_id(metadata.get("transactionId") or session.get("client_reference_id"), "transactionId")
    tenant_oid = parse_object_id(metadata.get("tenantId"), "tenantId")
    record_id = metadata.get("paymentRecordId")
    transaction = await db.transactions.find_one({"_id": transaction_oid, "tenantId": tenant_oid})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe transaction not found.")

    record = None
    if record_id:
        record = await db.payment_records.find_one({"_id": parse_object_id(record_id, "paymentRecordId"), "tenantId": tenant_oid})
    if not record and session.get("id"):
        record = await db.payment_records.find_one({"tenantId": tenant_oid, "transactionId": transaction_oid, "providerSessionId": session.get("id")})

    now = datetime.now(timezone.utc)
    paid_amount = float((session.get("amount_total") or 0) / 100)
    if record and record.get("status") in {"paid", "completed"}:
        return {"payment": serialize_document(record), "transaction": serialize_document(transaction), "alreadyProcessed": True}
    if record:
        # Capped at what the order still owes and claimed with a compare-and-set, exactly
        # as the gateway callback does. Without the status filter a record this flow had
        # already marked `failed` (superseded by another attempt, or expired) could be
        # resurrected to `paid`, crediting the order twice.
        live_summary = await _calculate_payment_summary(tenant_oid, transaction)
        creditable = round(min(paid_amount or float(record.get("amount", 0) or 0), float(live_summary["balance"])), 2)
        if creditable <= 0:
            return {"payment": _customer_safe_payment_record(record), "transaction": serialize_document(transaction), "alreadyProcessed": True}
        claimed = await db.payment_records.update_one(
            {"_id": record["_id"], "status": "pending_verification"},
            {"$set": {"status": "paid", "amount": creditable, "providerPaymentIntentId": session.get("payment_intent", ""), "referenceNumber": session.get("payment_intent") or session.get("id", ""), "notes": "Stripe Checkout payment completed.", "updatedAt": now}},
        )
        if not claimed.modified_count:
            return {"payment": serialize_document(record), "transaction": serialize_document(transaction), "alreadyProcessed": True}
        await _supersede_pending_attempts(db, transaction_oid, "stripe", keep_id=record["_id"])
        record_id = record["_id"]
    else:
        record = {
            "tenantId": tenant_oid,
            "transactionId": transaction_oid,
            "transactionNumber": transaction.get("transactionNumber", ""),
            "customerSnapshot": transaction.get("customerSnapshot", {}),
            "recordType": "payment",
            # Capped like the branch above. This fallback fires when no record matches
            # the session, and crediting the raw session amount here would credit more
            # than the order owes.
            "amount": round(min(paid_amount, float((await _calculate_payment_summary(tenant_oid, transaction))["balance"]) or paid_amount), 2),
            "currency": _stripe_currency_for(transaction),
            "method": "stripe_test",
            "methodLabel": _public_method_label("stripe_test"),
            "status": "paid",
            "referenceNumber": session.get("payment_intent") or session.get("id", ""),
            "notes": "Stripe Checkout payment completed.",
            "submittedBy": "stripe_webhook",
            "provider": "stripe",
            "providerMode": "test",
            "providerSessionId": session.get("id", ""),
            "providerPaymentIntentId": session.get("payment_intent", ""),
            "createdAt": now,
            "updatedAt": now,
        }
        record_id = (await db.payment_records.insert_one(record)).inserted_id

    updated_transaction = await _sync_transaction_payment_status(tenant_oid, transaction, None, "Stripe Checkout payment completed.")
    await create_business_notification(
        tenant_oid,
        "stripe_payment_paid",
        f"Stripe payment received for {transaction.get('transactionNumber', 'transaction')}",
        f"Stripe confirmed payment of {paid_amount:g}.",
        priority="high",
        metadata={"transactionId": str(transaction_oid), "paymentRecordId": str(record_id), "stripeSessionId": session.get("id", "")},
    )
    if updated_transaction.get("customerUserId"):
        await create_customer_notification(
            updated_transaction["customerUserId"],
            tenant_oid,
            "payment_paid",
            "Payment received",
            f"Your Stripe payment for {updated_transaction.get('transactionNumber', 'order')} was received.",
            {"transactionId": str(transaction_oid), "paymentRecordId": str(record_id)},
        )
    return {"payment": serialize_document(await db.payment_records.find_one({"_id": record_id})), "transaction": serialize_document(updated_transaction)}


async def sync_stripe_payment_record(tenant_id: str, payment_record_id: str, user: dict) -> dict[str, Any]:
    db = get_database()
    tenant_oid, _ = await _ensure_payment_access(tenant_id, user)
    record_oid = parse_object_id(payment_record_id, "paymentRecordId")
    record = await db.payment_records.find_one({"_id": record_oid, "tenantId": tenant_oid, "provider": "stripe"})
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe payment record not found.")
    transaction = await db.transactions.find_one({"_id": record["transactionId"], "tenantId": tenant_oid})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found for this Stripe payment.")
    session = await _retrieve_stripe_checkout_session(record.get("providerSessionId", ""))
    session = _ensure_session_metadata(session, transaction, record)
    now = datetime.now(timezone.utc)
    if stripe_session_is_paid(session):
        result = await mark_stripe_checkout_completed(session)
        await db.payment_records.update_one({"_id": record_oid}, {"$set": {"lastProviderSyncAt": now, "lastProviderSyncStatus": "paid"}})
        return {**result, "synced": True, "providerStatus": "paid"}
    await db.payment_records.update_one(
        {"_id": record_oid},
        {
            "$set": {
                "lastProviderSyncAt": now,
                "lastProviderSyncStatus": session.get("payment_status") or session.get("status") or "unknown",
                "notes": f"Stripe sync checked. Session status: {session.get('status', 'unknown')}; payment status: {session.get('payment_status', 'unknown')}.",
                "updatedAt": now,
            }
        },
    )
    return {
        "payment": serialize_document(await db.payment_records.find_one({"_id": record_oid})),
        "transaction": serialize_document(transaction),
        "synced": True,
        "providerStatus": session.get("payment_status") or session.get("status") or "unknown",
    }


async def sync_customer_stripe_checkout_session(order_id: str, session_id: str, current_user: dict) -> dict[str, Any]:
    db = get_database()
    transaction_oid = parse_object_id(order_id, "orderId")
    transaction = await db.transactions.find_one({"_id": transaction_oid, "customerUserId": current_user["_id"]})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    record = await db.payment_records.find_one(
        {
            "transactionId": transaction["_id"],
            "tenantId": transaction["tenantId"],
            "provider": "stripe",
            "providerSessionId": session_id,
        }
    )
    if not record:
        record = await db.payment_records.find_one(
            {
                "transactionId": transaction["_id"],
                "tenantId": transaction["tenantId"],
                "provider": "stripe",
                "status": "pending_verification",
            },
            sort=[("createdAt", -1)],
        )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe payment record not found for this order.")
    session = await _retrieve_stripe_checkout_session(session_id or record.get("providerSessionId", ""))
    session = _ensure_session_metadata(session, transaction, record)
    now = datetime.now(timezone.utc)
    if stripe_session_is_paid(session):
        result = await mark_stripe_checkout_completed(session)
        await db.payment_records.update_one({"_id": record["_id"]}, {"$set": {"lastProviderSyncAt": now, "lastProviderSyncStatus": "paid"}})
        return {**result, "synced": True, "providerStatus": "paid"}
    await db.payment_records.update_one(
        {"_id": record["_id"]},
        {"$set": {"lastProviderSyncAt": now, "lastProviderSyncStatus": session.get("payment_status") or session.get("status") or "unknown", "updatedAt": now}},
    )
    return {
        "payment": serialize_document(await db.payment_records.find_one({"_id": record["_id"]})),
        "transaction": serialize_document(transaction),
        "synced": True,
        "providerStatus": session.get("payment_status") or session.get("status") or "unknown",
    }


async def sync_public_stripe_checkout_session(slug: str, transaction_id: str, session_id: str) -> dict[str, Any]:
    db = get_database()
    tenant = await db.tenants.find_one({"slug": slug, "status": "active", "websiteStatus": "published"})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published business not found.")
    transaction_oid = parse_object_id(transaction_id, "transactionId")
    transaction = await db.transactions.find_one(
        {
            "_id": transaction_oid,
            "tenantId": tenant["_id"],
            "source": {"$in": ["public_website", "public_chat"]},
        }
    )
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public transaction not found.")
    record_query = {
        "transactionId": transaction["_id"],
        "tenantId": tenant["_id"],
        "provider": "stripe",
    }
    record = None
    if session_id:
        record = await db.payment_records.find_one({**record_query, "providerSessionId": session_id})
    if not record:
        record = await db.payment_records.find_one({**record_query, "status": "pending_verification"}, sort=[("createdAt", -1)])
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe payment record not found for this public order.")
    session = await _retrieve_stripe_checkout_session(session_id or record.get("providerSessionId", ""))
    session = _ensure_session_metadata(session, transaction, record)
    now = datetime.now(timezone.utc)
    if stripe_session_is_paid(session):
        result = await mark_stripe_checkout_completed(session)
        await db.payment_records.update_one({"_id": record["_id"]}, {"$set": {"lastProviderSyncAt": now, "lastProviderSyncStatus": "paid"}})
        return {
            **result,
            "payment": _customer_safe_payment_record(result.get("payment")),
            "transaction": customer_order_view(result.get("transaction") or transaction),
            "synced": True,
            "providerStatus": "paid",
        }
    await db.payment_records.update_one(
        {"_id": record["_id"]},
        {"$set": {"lastProviderSyncAt": now, "lastProviderSyncStatus": session.get("payment_status") or session.get("status") or "unknown", "updatedAt": now}},
    )
    return {
        # This endpoint needs no account at all, so the record must be stripped like
        # every other customer-facing one. It was returning the owner's decision notes,
        # the internal actor ids and the raw provider response.
        "payment": _customer_safe_payment_record(await db.payment_records.find_one({"_id": record["_id"]})),
        "transaction": customer_order_view(transaction),
        "synced": True,
        "providerStatus": session.get("payment_status") or session.get("status") or "unknown",
    }


async def process_stripe_webhook(payload: bytes, signature_header: str) -> dict[str, Any]:
    if not _verify_stripe_signature(payload, signature_header):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe webhook signature.")
    try:
        event = httpx.Response(200, content=payload).json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe webhook payload.") from exc
    db = get_database()
    event_type = event.get("type", "")
    event_id = event.get("id") or hashlib.sha256(payload).hexdigest()
    session = (event.get("data") or {}).get("object") or {}
    metadata = session.get("metadata") or {}
    tenant_oid = None
    if metadata.get("tenantId"):
        try:
            tenant_oid = parse_object_id(metadata.get("tenantId"), "tenantId")
        except HTTPException:
            tenant_oid = None
    now = datetime.now(timezone.utc)
    # Claim the event atomically. Checking for "processed" and then writing "processing"
    # as two steps let two concurrent deliveries of the same event both observe
    # "processing" and both credit the order. The filter rejects an event already in
    # either state, so exactly one delivery proceeds.
    #
    # `upsert` cannot be used together with a filter that excludes the existing row:
    # `eventId` carries a unique index, so when a claim is already held Mongo tries to
    # INSERT a second document and raises DuplicateKeyError instead of returning None.
    # That turned every ordinary Stripe retry into a 500, so Stripe retried forever.
    # The claim is therefore attempted in two steps that are each atomic on their own.
    claim_update = {
        "$set": {
            "eventType": event_type,
            "tenantId": tenant_oid,
            "transactionId": metadata.get("transactionId", ""),
            "paymentRecordId": metadata.get("paymentRecordId", ""),
            "stripeObjectId": session.get("id", ""),
            "status": "processing",
            "updatedAt": now,
        },
    }
    claim = await db.stripe_webhook_events.find_one_and_update(
        {"eventId": event_id, "status": {"$nin": ["processing", "processed"]}},
        claim_update,
        return_document=ReturnDocument.AFTER,
    )
    if claim is None:
        # Either this event has never been seen, or another delivery already holds the
        # claim. Inserting decides which: the unique index lets exactly one caller win.
        try:
            await db.stripe_webhook_events.insert_one(
                {"eventId": event_id, "createdAt": now, **claim_update["$set"]}
            )
        except DuplicateKeyError:
            return {"processed": False, "duplicate": True, "eventType": event_type}
    try:
        # `completed` fires when the customer finishes the flow, which for a
        # delayed-notification method is before the money arrives; Stripe then sends
        # `async_payment_succeeded` once it actually has. Settling on `completed` alone
        # marked unpaid orders as paid.
        if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"} and stripe_session_is_paid(session):
            data = await mark_stripe_checkout_completed(session)
            await db.stripe_webhook_events.update_one({"eventId": event_id}, {"$set": {"status": "processed", "processedAt": datetime.now(timezone.utc), "error": ""}})
            return {"processed": True, "eventType": event_type, **data}
        await db.stripe_webhook_events.update_one({"eventId": event_id}, {"$set": {"status": "ignored", "processedAt": datetime.now(timezone.utc), "error": ""}})
        return {"processed": False, "eventType": event_type}
    except Exception as exc:
        await db.stripe_webhook_events.update_one({"eventId": event_id}, {"$set": {"status": "failed", "processedAt": datetime.now(timezone.utc), "error": str(exc)}})
        raise


# --- Redirect payment gateways (JazzCash, Easypaisa) ---------------------------------
#
# The shape mirrors the Stripe flow above: create a pending payment_record, send the
# customer to the gateway, and let the signed callback move that record to paid and
# resync the transaction. Keeping one shape means the Transactions and Payments screens,
# receipts, and refunds work for every provider without special cases.


def _gateway_return_url(provider: str) -> str:
    return f"{gateways._api_base_url()}/payments/{provider}/callback"


def _frontend_order_url(order_id: str, status_value: str) -> str:
    base = (settings.frontend_base_url or "http://localhost:5173").rstrip("/")
    path = settings.payment_return_path.replace("{orderId}", str(order_id)).replace("{status}", status_value)
    return f"{base}{path}"


def _build_gateway_txn_ref(record_id: Any) -> str:
    """Reference the gateway echoes back, used to find the record again.

    JazzCash requires this to be unique per attempt and alphanumeric, so the payment
    record id carries the linkage rather than the order id: one order can have several
    attempts, and each needs its own reference.
    """
    return f"BZX{str(record_id)}"


def _record_id_from_txn_ref(txn_ref: str) -> str:
    return str(txn_ref or "").strip().removeprefix("BZX")


async def create_gateway_checkout(order_id: str, provider: str, current_user: dict) -> dict[str, Any]:
    """Start a JazzCash or Easypaisa payment for an existing order."""
    if provider not in ONLINE_GATEWAY_METHODS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported payment gateway.")
    gateway = providers.get_provider(provider)
    if gateway.flow == FLOW_OTP:
        # This wallet is configured for the emailed-code flow, which has no redirect and
        # its own endpoints. Say so rather than returning a checkout that cannot exist.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{gateway.label} is set up for verification-code payments. Use the wallet checkout instead.",
        )
    if not gateway.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{gateway.label} is not configured for online payments yet.",
        )

    db = get_database()
    transaction_oid = parse_object_id(order_id, "orderId")
    transaction = await db.transactions.find_one({"_id": transaction_oid, "customerUserId": current_user["_id"]})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    if transaction.get("transactionType") not in PAYABLE_TRANSACTION_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction cannot be paid online.")

    tenant_oid = transaction["tenantId"]
    payment_options = await get_customer_payment_options_for_tenant(tenant_oid)
    normalize_customer_payment_preference(provider, payment_options)

    summary = await _calculate_payment_summary(tenant_oid, transaction)
    balance = summary["balance"]
    if balance <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction has no remaining balance.")

    now = datetime.now(timezone.utc)
    customer_snapshot = transaction.get("customerSnapshot") or {}
    record = {
        "tenantId": tenant_oid,
        "transactionId": transaction["_id"],
        "transactionNumber": transaction.get("transactionNumber", ""),
        "customerSnapshot": customer_snapshot,
        "recordType": "payment",
        "amount": float(balance),
        "currency": (transaction.get("pricing") or {}).get("currency") or "PKR",
        "method": provider,
        "methodLabel": _public_method_label(provider),
        "status": "pending_verification",
        "referenceNumber": "",
        "notes": f"{gateway.label} checkout started.",
        "flow": gateway.flow,
        "submittedBy": "customer",
        "provider": provider,
        "providerMode": gateways.gateway_mode(provider),
        "providerSessionId": "",
        "providerTransactionId": "",
        "createdBy": current_user["_id"],
        "createdAt": now,
        "updatedAt": now,
    }
    # Close the previous abandoned attempt, so the order does not accumulate pending
    # records that each keep it showing as awaiting owner review.
    await _supersede_pending_attempts(db, transaction["_id"], provider)
    record["_id"] = (await db.payment_records.insert_one(record)).inserted_id

    txn_ref = _build_gateway_txn_ref(record["_id"])
    context = PaymentContext(
        provider=provider,
        reference=txn_ref,
        amount=float(balance),
        currency=record["currency"],
        order_id=str(transaction["_id"]),
        order_number=transaction.get("transactionNumber", ""),
        tenant_id=str(tenant_oid),
        customer_name=str(customer_snapshot.get("name") or ""),
        customer_email=str(customer_snapshot.get("email") or current_user.get("email") or ""),
        customer_mobile=str(customer_snapshot.get("phone") or ""),
        return_url=_gateway_return_url(provider),
    )
    try:
        initiation = await gateway.initiate(context)
    except PaymentProviderError as exc:
        await db.payment_records.update_one(
            {"_id": record["_id"]},
            {"$set": {"status": "failed", "notes": f"Could not start {gateway.label}: {exc}", "updatedAt": datetime.now(timezone.utc)}},
        )
        logger.warning("Payment provider error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider could not be reached just now. Please try again in a moment.",
        ) from exc
    checkout = {
        "url": initiation.redirect.url,
        "method": initiation.redirect.method,
        "fields": initiation.redirect.fields,
        "simulated": initiation.simulated,
    }

    await db.payment_records.update_one(
        {"_id": record["_id"]},
        {"$set": {"providerSessionId": txn_ref, "referenceNumber": txn_ref, "updatedAt": datetime.now(timezone.utc)}},
    )
    updated_transaction = await _sync_transaction_payment_status(
        tenant_oid, transaction, current_user.get("_id"), f"{gateways.gateway_label(provider)} checkout started."
    )
    await create_business_notification(
        tenant_oid,
        "gateway_checkout_created",
        f"{gateways.gateway_label(provider)} checkout started for {transaction.get('transactionNumber', 'transaction')}",
        f"Customer opened {gateways.gateway_label(provider)} for {float(balance):g}.",
        priority="medium",
        metadata={"transactionId": str(transaction["_id"]), "paymentRecordId": str(record["_id"]), "provider": provider},
    )
    return {
        "provider": provider,
        "label": gateways.gateway_label(provider),
        "mode": gateways.gateway_mode(provider),
        "simulated": bool(checkout.get("simulated")),
        "redirect": {"url": checkout["url"], "method": checkout["method"], "fields": checkout.get("fields") or {}},
        "paymentRecordId": str(record["_id"]),
        "txnRef": txn_ref,
        "amount": float(balance),
        "transaction": serialize_document(updated_transaction),
    }


async def complete_gateway_payment(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply a gateway callback to the payment record it refers to.

    Returns where to send the customer next. This is a public endpoint, so nothing here
    trusts the payload beyond what the signature covers, and a replayed callback for an
    already-paid record is a no-op rather than a second payment.
    """
    if provider not in ONLINE_GATEWAY_METHODS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported payment gateway.")

    # A gateway whose credentials are the built-in placeholders must never be able to
    # settle a real order: the simulator salt is published in this repository, so any
    # caller could sign a payload with it.
    gateway_provider = providers.get_provider(provider)
    if not gateway_provider.is_available():
        logger.error("Refusing %s callback: the provider is not available in this environment.", provider)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment reference not recognised.")

    result = gateways.verify_callback(provider, payload)
    db = get_database()
    record_id = _record_id_from_txn_ref(result.get("txnRef"))
    record = None
    if record_id:
        try:
            # The callback may only ever settle the record it actually belongs to.
            # Matching on the id alone let a JazzCash callback mark a Stripe, manual or
            # OTP record paid, because every checkout hands the customer its record id.
            record = await db.payment_records.find_one(
                {"_id": ObjectId(record_id), "provider": provider, "flow": FLOW_REDIRECT}
            )
        except Exception:
            record = None
    if not record:
        logger.warning("Ignoring %s callback for unknown reference %r.", provider, result.get("txnRef"))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment reference not recognised.")

    order_id = str(record["transactionId"])
    if not result["signatureValid"]:
        # A signature that does not verify proves nothing about the payment, so it must
        # not change the record either: an unauthenticated caller could otherwise fail
        # any pending payment at will. Log it and stop.
        logger.error("Rejecting %s callback for %s: signature did not verify.", provider, result.get("txnRef"))
        return {"paid": False, "redirectUrl": _frontend_order_url(order_id, "failed"), "reason": "invalid_signature"}

    if record.get("status") in {"paid", "completed"}:
        return {"paid": True, "redirectUrl": _frontend_order_url(order_id, "success"), "alreadyProcessed": True}

    if record.get("status") != "pending_verification":
        logger.warning("Ignoring %s callback for record %s in state %r.", provider, record["_id"], record.get("status"))
        return {"paid": False, "redirectUrl": _frontend_order_url(order_id, "failed"), "reason": "not_awaiting_payment"}

    now = datetime.now(timezone.utc)
    if not result["paid"]:
        await db.payment_records.update_one(
            {"_id": record["_id"]},
            {"$set": {
                "status": "failed",
                "notes": result.get("responseMessage") or "Payment was not completed.",
                "providerResponseCode": result.get("responseCode", ""),
                "updatedAt": now,
            }},
        )
        # Without this the order keeps the "pending_verification" it was given when the
        # attempt started, so an abandoned payment would look like one awaiting review.
        transaction = await db.transactions.find_one({"_id": record["transactionId"], "tenantId": record["tenantId"]})
        if transaction:
            await _sync_transaction_payment_status(
                record["tenantId"], transaction, None, f"{gateways.gateway_label(provider)} payment was not completed."
            )
        return {"paid": False, "redirectUrl": _frontend_order_url(order_id, "cancelled"), "reason": result.get("responseCode", "")}

    transaction = await db.transactions.find_one({"_id": record["transactionId"], "tenantId": record["tenantId"]})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found for this payment.")

    # The gateway's amount is authoritative: a customer who pays less than the balance
    # must not close the order.
    if not result.get("outcomeSigned", True):
        # The gateway's signature covers the request we sent, not the outcome it is
        # reporting, and the customer holds that same signature. Crediting on it would
        # let anyone mark their own order paid, so hold the payment for the owner to
        # confirm against the gateway's own dashboard instead.
        await db.payment_records.update_one(
            {"_id": record["_id"], "status": "pending_verification"},
            {"$set": {
                "needsOwnerReview": True,
                "providerTransactionId": result.get("providerTransactionId", ""),
                "providerResponseCode": result.get("responseCode", ""),
                "notes": (
                    f"{gateways.gateway_label(provider)} reported this as paid, but its callback signature does "
                    "not cover the payment outcome. Confirm the payment in your gateway dashboard before accepting it."
                ),
                "updatedAt": datetime.now(timezone.utc),
            }},
        )
        await create_business_notification(
            record["tenantId"],
            "gateway_payment_needs_review",
            f"{gateways.gateway_label(provider)} payment needs confirmation for {transaction.get('transactionNumber', 'transaction')}",
            (
                f"{gateways.gateway_label(provider)} reported a payment of {float(result.get('amount') or 0):g}, but its "
                "callback cannot be trusted on its own. Confirm it in your gateway dashboard, then approve the payment."
            ),
            priority="high",
            metadata={"transactionId": order_id, "paymentRecordId": str(record["_id"]), "provider": provider},
        )
        return {
            "paid": False,
            "redirectUrl": _frontend_order_url(order_id, "pending"),
            "reason": "awaiting_owner_confirmation",
        }

    # Re-read the balance at settlement rather than trusting the amount this attempt was
    # opened with. Without this, two attempts opened back to back could each credit the
    # full total, and a partial payment taken in between would be credited twice over.
    # The OTP path already did this; the gateway callback did not.
    reported_amount = float(result.get("amount") or 0) or float(record.get("amount", 0))
    live_summary = await _calculate_payment_summary(record["tenantId"], transaction)
    paid_amount = round(min(reported_amount, float(live_summary["balance"])), 2)
    if paid_amount <= 0:
        logger.info("Ignoring %s callback for %s: the order has no outstanding balance.", provider, order_id)
        return {"paid": True, "redirectUrl": _frontend_order_url(order_id, "success"), "alreadyProcessed": True}

    # Claim the record so two concurrent deliveries of the same callback cannot both
    # credit the order.
    claimed = await db.payment_records.update_one(
        {"_id": record["_id"], "status": "pending_verification"},
        {"$set": {
            "status": "paid",
            "amount": paid_amount,
            "providerTransactionId": result.get("providerTransactionId", ""),
            "referenceNumber": result.get("providerTransactionId") or record.get("referenceNumber", ""),
            "providerResponseCode": result.get("responseCode", ""),
            "notes": result.get("responseMessage") or f"{gateways.gateway_label(provider)} payment completed.",
            "verification": {"verifiedByUserId": None, "verifiedAt": now, "verifiedBy": f"{provider}_callback"},
            "updatedAt": now,
        }},
    )
    if not claimed.modified_count:
        # Another delivery of the same callback got there first and has already credited
        # the order; crediting again here would double the recorded payment.
        return {"paid": True, "redirectUrl": _frontend_order_url(order_id, "success"), "alreadyProcessed": True}

    updated_transaction = await _sync_transaction_payment_status(
        record["tenantId"], transaction, None, f"{gateways.gateway_label(provider)} payment completed."
    )
    await create_business_notification(
        record["tenantId"],
        "gateway_payment_paid",
        f"{gateways.gateway_label(provider)} payment received for {transaction.get('transactionNumber', 'transaction')}",
        f"{gateways.gateway_label(provider)} confirmed payment of {paid_amount:g}.",
        priority="high",
        metadata={"transactionId": order_id, "paymentRecordId": str(record["_id"]), "provider": provider},
    )
    if updated_transaction.get("customerUserId"):
        await create_customer_notification(
            updated_transaction["customerUserId"],
            record["tenantId"],
            "payment_paid",
            "Payment received",
            f"Your {gateways.gateway_label(provider)} payment for {updated_transaction.get('transactionNumber', 'order')} was received.",
            {"transactionId": order_id, "paymentRecordId": str(record["_id"])},
        )
    return {
        "paid": True,
        "redirectUrl": _frontend_order_url(order_id, "success"),
        "paymentRecordId": str(record["_id"]),
        "amount": paid_amount,
    }


async def get_gateway_simulator_context(provider: str, txn_ref: str) -> dict[str, Any]:
    """Details the local simulator page needs to stand in for a real gateway."""
    if not gateways.is_simulated(provider):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment simulator is not enabled.")
    db = get_database()
    record_id = _record_id_from_txn_ref(txn_ref)
    try:
        record = await db.payment_records.find_one({"_id": ObjectId(record_id)})
    except Exception:
        record = None
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment reference not recognised.")
    tenant = await db.tenants.find_one({"_id": record["tenantId"]}) or {}
    return {
        "provider": provider,
        "label": gateways.gateway_label(provider),
        "txnRef": txn_ref,
        "amount": float(record.get("amount", 0)),
        "currency": record.get("currency", "PKR"),
        "businessName": tenant.get("name", ""),
        "transactionNumber": record.get("transactionNumber", ""),
        "alreadyPaid": record.get("status") in {"paid", "completed"},
    }


async def apply_simulated_gateway_result(provider: str, txn_ref: str, approve: bool) -> dict[str, Any]:
    """Sign a simulated outcome and push it through the real callback path."""
    if not gateways.is_simulated(provider):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment simulator is not enabled.")
    context = await get_gateway_simulator_context(provider, txn_ref)
    payload = gateways.build_simulated_callback(provider, txn_ref=txn_ref, amount=context["amount"], approve=approve)
    return await complete_gateway_payment(provider, payload)


# --------------------------------------------------------------- OTP wallet flow --


def _wallet_provider_or_422(provider_code: str):
    """Resolve a wallet that is actually configured for the emailed-code flow."""
    try:
        provider = providers.get_provider(provider_code)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported payment method.") from exc
    if provider.flow != FLOW_OTP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{provider.label} is not set up for code-based payments on this server.",
        )
    if not provider.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider.label} is not available right now.",
        )
    return provider


def _customer_payment_email(current_user: dict, transaction: dict) -> str:
    """The address a payment code may be sent to.

    Read from the signed-in account, never from the request. If a caller could name the
    recipient they could have any customer's payment code delivered to themselves.
    """
    return str(current_user.get("email") or "").strip().lower()


async def _load_customer_order_for_payment(order_id: str, current_user: dict) -> dict:
    db = get_database()
    transaction_oid = parse_object_id(order_id, "orderId")
    transaction = await db.transactions.find_one({"_id": transaction_oid, "customerUserId": current_user["_id"]})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    if transaction.get("transactionType") not in PAYABLE_TRANSACTION_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction cannot be paid online.")
    return transaction


def _wallet_payment_view(record: dict, transaction: dict, provider, challenge: dict) -> dict[str, Any]:
    """The envelope the checkout screen works from.

    Carries the amount the server computed, the masked destination, and the counters a
    countdown needs. It does not carry the code, in any mode.
    """
    return {
        "paymentRecordId": str(record["_id"]),
        "provider": provider.code,
        "label": provider.label,
        "flow": provider.flow,
        "mode": provider.mode(),
        "simulated": True,
        "amount": float(record.get("amount", 0)),
        "currency": record.get("currency", "PKR"),
        "mobileNumber": record.get("customerMobile", ""),
        "demoNotice": "Simulated payment for demonstration. No real money is transferred.",
        **challenge,
        "transaction": serialize_document(transaction),
    }


async def start_wallet_otp_payment(order_id: str, provider_code: str, mobile_number: str, current_user: dict) -> dict[str, Any]:
    """Begin an emailed-code payment for the full outstanding balance of an order."""
    db = get_database()
    provider = _wallet_provider_or_422(provider_code)
    transaction = await _load_customer_order_for_payment(order_id, current_user)
    tenant_oid = transaction["tenantId"]

    # The business must actually offer this wallet. Reusing the shared normalizer keeps
    # one answer to "is this method enabled here".
    payment_options = await get_customer_payment_options_for_tenant(tenant_oid, allow_otp=True)
    normalize_customer_payment_preference(provider.code, payment_options)

    customer_email = _customer_payment_email(current_user, transaction)
    if not customer_email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please add an email to your profile to pay this way.",
        )

    normalized_mobile = normalize_optional_pk_phone(mobile_number)
    if not normalized_mobile:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter the mobile number registered with your wallet.")

    # The amount always comes from the order, never from the request, and an OTP payment
    # always settles the whole outstanding balance.
    summary = await _calculate_payment_summary(tenant_oid, transaction)
    balance = summary["balance"]
    if balance <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This order is already paid.")

    tenant = await db.tenants.find_one({"_id": tenant_oid})
    # Close any earlier unfinished attempt before opening a new one, so two codes cannot
    # both be verified against the same balance.
    await _supersede_pending_attempts(db, transaction["_id"], provider.code)
    now = datetime.now(timezone.utc)
    currency = (transaction.get("pricing") or {}).get("currency") or "PKR"
    record = {
        "tenantId": tenant_oid,
        "transactionId": transaction["_id"],
        "transactionNumber": transaction.get("transactionNumber", ""),
        "customerSnapshot": transaction.get("customerSnapshot", {}),
        "recordType": "payment",
        "amount": float(balance),
        "currency": currency,
        "method": provider.code,
        "methodLabel": _public_method_label(provider.code),
        "status": "pending_verification",
        "referenceNumber": "",
        "notes": f"{provider.label} demo payment started.",
        "submittedBy": "customer",
        "provider": provider.code,
        "providerMode": provider.mode(),
        "flow": FLOW_OTP,
        # Recorded for the receipt and for the owner's audit trail. In a real wallet this
        # identifies the payer's account; in the demo it identifies nothing and is
        # deliberately not used in any decision.
        "customerMobile": normalized_mobile,
        "providerSessionId": "",
        "providerTransactionId": "",
        "createdBy": current_user["_id"],
        "createdAt": now,
        "updatedAt": now,
    }
    record["_id"] = (await db.payment_records.insert_one(record)).inserted_id

    context = PaymentContext(
        provider=provider.code,
        reference=str(record["_id"]),
        amount=float(balance),
        currency=currency,
        order_id=str(transaction["_id"]),
        order_number=transaction.get("transactionNumber", ""),
        tenant_id=str(tenant_oid),
        business_name=(tenant or {}).get("name", ""),
        customer_name=str((transaction.get("customerSnapshot") or {}).get("name") or current_user.get("fullName", "")),
        customer_email=customer_email,
        customer_mobile=normalized_mobile,
    )
    try:
        initiation = await provider.initiate(context)
    except PaymentProviderError as exc:
        await db.payment_records.update_one(
            {"_id": record["_id"]},
            {"$set": {"status": "failed", "notes": str(exc), "updatedAt": datetime.now(timezone.utc)}},
        )
        logger.warning("Payment provider rejected the request: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That payment could not be started. Please try a different payment method.",
        ) from exc

    challenge = await payment_otp_service.start_payment_challenge(
        payment_record_id=record["_id"],
        tenant_id=tenant_oid,
        transaction_id=transaction["_id"],
        provider=provider.code,
        challenge=initiation.challenge,
        customer_email=customer_email,
        amount=float(balance),
        currency=currency,
        business_name=(tenant or {}).get("name", ""),
        order_number=transaction.get("transactionNumber", ""),
        provider_label=provider.label,
    )

    await db.payment_records.update_one(
        {"_id": record["_id"]},
        {"$set": {
            "providerSessionId": str(record["_id"]),
            "referenceNumber": str(record["_id"]),
            "otpChallengeId": ObjectId(challenge["challengeId"]),
            "notes": initiation.notes,
            "updatedAt": datetime.now(timezone.utc),
        }},
    )
    record["providerSessionId"] = str(record["_id"])
    updated_transaction = await _sync_transaction_payment_status(
        tenant_oid, transaction, current_user.get("_id"), f"{provider.label} demo payment started."
    )
    await create_business_notification(
        tenant_oid,
        "wallet_otp_checkout_created",
        f"{provider.label} demo payment started for {transaction.get('transactionNumber', 'transaction')}",
        f"Customer started a {provider.label} verification-code payment of {float(balance):g}.",
        priority="medium",
        metadata={"transactionId": str(transaction["_id"]), "paymentRecordId": str(record["_id"]), "provider": provider.code},
    )
    return _wallet_payment_view(record, updated_transaction, provider, challenge)


async def _load_wallet_payment_record(order_id: str, payment_record_id: str, current_user: dict) -> tuple[dict, dict]:
    db = get_database()
    transaction = await _load_customer_order_for_payment(order_id, current_user)
    record = await db.payment_records.find_one(
        {
            "_id": parse_object_id(payment_record_id, "paymentRecordId"),
            "transactionId": transaction["_id"],
            "tenantId": transaction["tenantId"],
        }
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment attempt not found.")
    if record.get("flow") != FLOW_OTP:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This payment does not use a verification code.")
    return transaction, record


async def verify_wallet_otp_payment(order_id: str, payment_record_id: str, code: str, current_user: dict) -> dict[str, Any]:
    """Settle an emailed-code payment when the right code comes back."""
    db = get_database()
    transaction, record = await _load_wallet_payment_record(order_id, payment_record_id, current_user)
    provider = _wallet_provider_or_422(record.get("provider", ""))

    # A replayed submission for a payment already settled is a no-op, not a second
    # payment. The redirect gateways behave the same way on a repeated callback.
    if record.get("status") in {"paid", "completed"}:
        return {
            "paid": True,
            "alreadyProcessed": True,
            "payment": serialize_document(record),
            "transaction": serialize_document(transaction),
        }

    challenge = await payment_otp_service.consume_challenge(record["_id"], provider.code, code)

    context = PaymentContext(
        provider=provider.code,
        reference=str(record["_id"]),
        amount=float(record.get("amount", 0)),
        currency=record.get("currency", "PKR"),
        order_id=str(transaction["_id"]),
        order_number=transaction.get("transactionNumber", ""),
        tenant_id=str(transaction["tenantId"]),
    )
    # The provider checks the code again against the stored hash. Redundant after
    # consume_challenge, and deliberately so: the provider stays self-contained, and a
    # future caller that forgets the challenge step still cannot settle on a wrong code.
    confirmation = await provider.confirm(
        context,
        {"code": code, "codeHash": challenge.get("codeHash", ""), "paymentRecordId": str(record["_id"])},
    )
    if not confirmation.paid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect code. Request a new one and try again.")

    # Re-read the balance at settlement, not at the time the attempt started. Crediting
    # the stored amount let two attempts opened back to back each settle the full total.
    live_summary = await _calculate_payment_summary(transaction["tenantId"], transaction)
    creditable = min(float(record.get("amount", 0) or 0), float(live_summary["balance"]))
    if creditable <= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This order has already been paid.")

    now = datetime.now(timezone.utc)
    settled = await db.payment_records.update_one(
        {"_id": record["_id"], "status": "pending_verification"},
        {"$set": {
            "status": "paid",
            "amount": creditable,
            "providerTransactionId": confirmation.provider_transaction_id,
            "referenceNumber": confirmation.provider_transaction_id or record.get("referenceNumber", ""),
            "providerResponseCode": confirmation.response_code,
            "notes": confirmation.response_message,
            "verification": {
                "requiresOwnerApproval": False,
                "verifiedByUserId": current_user.get("_id"),
                "verifiedAt": now,
            },
            "paidAt": now,
            "updatedAt": now,
        }},
    )
    if not settled.modified_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This payment has already been settled.")
    await _supersede_pending_attempts(db, transaction["_id"], provider.code, keep_id=record["_id"])
    tenant = await db.tenants.find_one({"_id": transaction["tenantId"]})
    updated_transaction = await _sync_transaction_payment_status(
        transaction["tenantId"], transaction, current_user.get("_id"), f"{provider.label} demo payment verified."
    )
    await create_business_notification(
        transaction["tenantId"],
        "payment_recorded",
        f"{provider.label} payment received for {transaction.get('transactionNumber', 'transaction')}",
        f"{float(record.get('amount', 0)):g} settled through the {provider.label} verification-code flow.",
        priority="high",
        metadata={
            "transactionId": str(transaction["_id"]),
            "paymentRecordId": str(record["_id"]),
            "provider": provider.code,
            "tenantSlug": (tenant or {}).get("slug", ""),
        },
    )
    await create_customer_notification(
        current_user["_id"],
        transaction["tenantId"],
        "payment_updated",
        f"Payment confirmed for {transaction.get('transactionNumber', 'your order')}",
        f"Your {provider.label} payment of {float(record.get('amount', 0)):g} was confirmed.",
        {"transactionId": str(transaction["_id"]), "tenantSlug": (tenant or {}).get("slug", "")},
    )
    settled_record = await db.payment_records.find_one({"_id": record["_id"]})
    return {
        "paid": True,
        "payment": serialize_document(settled_record),
        "transaction": serialize_document(updated_transaction),
    }


async def resend_wallet_otp_payment(order_id: str, payment_record_id: str, current_user: dict) -> dict[str, Any]:
    """Issue a new code, invalidating the previous one."""
    db = get_database()
    transaction, record = await _load_wallet_payment_record(order_id, payment_record_id, current_user)
    provider = _wallet_provider_or_422(record.get("provider", ""))

    if record.get("status") in {"paid", "completed"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This payment is already complete.")

    customer_email = _customer_payment_email(current_user, transaction)
    if not customer_email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please add an email to your profile to pay this way.",
        )

    tenant = await db.tenants.find_one({"_id": transaction["tenantId"]})
    context = PaymentContext(
        provider=provider.code,
        reference=str(record["_id"]),
        amount=float(record.get("amount", 0)),
        currency=record.get("currency", "PKR"),
        order_id=str(transaction["_id"]),
        order_number=transaction.get("transactionNumber", ""),
        tenant_id=str(transaction["tenantId"]),
        business_name=(tenant or {}).get("name", ""),
        customer_email=customer_email,
        customer_mobile=record.get("customerMobile", ""),
    )
    try:
        initiation = await provider.initiate(context)
    except PaymentProviderError as exc:
        logger.warning("Payment provider rejected the request: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That payment could not be started. Please try a different payment method.",
        ) from exc

    challenge = await payment_otp_service.start_payment_challenge(
        payment_record_id=record["_id"],
        tenant_id=transaction["tenantId"],
        transaction_id=transaction["_id"],
        provider=provider.code,
        challenge=initiation.challenge,
        customer_email=customer_email,
        amount=float(record.get("amount", 0)),
        currency=record.get("currency", "PKR"),
        business_name=(tenant or {}).get("name", ""),
        order_number=transaction.get("transactionNumber", ""),
        provider_label=provider.label,
        is_resend=True,
    )
    await db.payment_records.update_one(
        {"_id": record["_id"]},
        {"$set": {"otpChallengeId": ObjectId(challenge["challengeId"]), "updatedAt": datetime.now(timezone.utc)}},
    )
    return _wallet_payment_view(record, transaction, provider, challenge)
