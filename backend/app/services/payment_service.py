from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from html import escape
from typing import Any
from urllib.parse import urljoin

import httpx
from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.module_guard import ensure_tenant_module_enabled
from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database
from app.services.business_notification_service import create_business_notification
from app.services.inventory_service import restore_transaction_stock
from app.services.customer_notification_service import create_customer_notification
from app.services.storage_service import store_payment_proof_image
from app.services.transaction_workflow_service import get_allowed_payment_statuses

PAYMENT_METHODS = {"cod", "manual_bank", "bank_transfer", "jazzcash_mock", "easypaisa_mock", "stripe_test", "manual", "jazzcash", "easypaisa", "stripe", "card", "online_card"}
CANONICAL_PAYMENT_METHODS = {"cod", "manual_bank", "jazzcash_mock", "easypaisa_mock", "stripe_test"}
PAYMENT_METHOD_ALIASES = {
    "manual": "manual_bank",
    "bank": "manual_bank",
    "bank_transfer": "manual_bank",
    "manual_transfer": "manual_bank",
    "jazzcash": "jazzcash_mock",
    "jazz_cash": "jazzcash_mock",
    "easypaisa": "easypaisa_mock",
    "easy_paisa": "easypaisa_mock",
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
        "jazzcash_mock": "JazzCash mock",
        "easypaisa_mock": "EasyPaisa mock",
        "stripe_test": "Stripe test card",
    }.get(method, method.replace("_", " ").title())


def _enabled_method_codes(settings_doc: dict) -> list[str]:
    methods: list[str] = []
    if settings_doc.get("codEnabled"):
        methods.append("cod")
    if settings_doc.get("manualEnabled") or settings_doc.get("bankTransferEnabled"):
        methods.append("manual_bank")
    if settings_doc.get("jazzCashEnabled"):
        methods.append("jazzcash_mock")
    if settings_doc.get("easyPaisaEnabled"):
        methods.append("easypaisa_mock")
    if settings_doc.get("stripeEnabled"):
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
    if method == "stripe_test":
        return {
            "code": method,
            "label": _public_method_label(method),
            "description": "Pay online with Stripe Checkout using a test card such as 4242 4242 4242 4242.",
            "requiresOwnerApproval": False,
            "isOnline": True,
            "provider": "stripe",
            "testCard": "4242 4242 4242 4242",
        }
    return {"code": method, "label": _public_method_label(method), "description": "", "requiresOwnerApproval": True}


def serialize_customer_payment_options(settings_doc: dict | None) -> dict[str, Any]:
    settings_doc = settings_doc or {}
    if not settings_doc:
        settings_doc = _default_settings(ObjectId())
    enabled = _enabled_method_codes(settings_doc)
    methods = [_method_customer_details(settings_doc, method) for method in enabled]
    default_method = settings_doc.get("defaultMethod") or (enabled[0] if enabled else "cod")
    if default_method not in enabled and enabled:
        default_method = enabled[0]
    return {
        "enabled": bool(methods),
        "defaultMethod": default_method,
        "methods": methods,
        "customerInstructions": settings_doc.get("customerInstructions", ""),
        "paymentsDemoMode": bool(settings_doc.get("paymentsDemoMode", True)),
        "requireOwnerApproval": bool(settings_doc.get("requireOwnerApproval", True)),
    }


async def get_customer_payment_options_for_tenant(tenant_oid: ObjectId) -> dict[str, Any]:
    db = get_database()
    settings = await db.payment_settings.find_one({"tenantId": tenant_oid})
    if not settings:
        settings = _default_settings(tenant_oid)
        settings["_id"] = (await db.payment_settings.insert_one(settings)).inserted_id
    return serialize_customer_payment_options(settings)


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


async def list_customer_payment_records_for_transaction(transaction: dict) -> list[dict[str, Any]]:
    db = get_database()
    cursor = db.payment_records.find({"transactionId": transaction["_id"]}).sort("createdAt", -1)
    return [serialize_document(record) async for record in cursor]


async def summarize_payment_records_for_transaction(transaction: dict, db=None) -> dict[str, Any]:
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
        "latest": serialize_document(latest) if latest else None,
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
    return _build_payment_receipt_html(tenant, transaction, record)


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
    net_paid = max(0.0, paid - refunded)
    balance = max(0.0, total - net_paid)
    return {"total": total, "paid": net_paid, "pending": pending, "cod": cod, "rejected": rejected, "refunded": refunded, "balance": balance}


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


async def _sync_transaction_payment_status(tenant_oid: ObjectId, transaction: dict, actor_user_id: ObjectId | None, note: str) -> dict:
    db = get_database()
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
    return await db.transactions.find_one({"_id": transaction["_id"]})


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
    payment_options = transaction.get("paymentInstructions") or await get_customer_payment_options_for_tenant(tenant_oid)
    selected_method = _normalize_method(method or (transaction.get("paymentPreference") or {}).get("method") or payment_options.get("defaultMethod"))
    if selected_method == "cod":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="COD does not require payment proof. The business will collect cash directly.")
    normalize_customer_payment_preference(selected_method, payment_options)

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

    await db.payment_records.update_one(
        {"_id": record_oid},
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
    records = [serialize_document(row) async for row in records_cursor]

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
    if record_status in {"paid", "cod"} and payload.amount > current_summary["balance"] + 0.01:
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


def _verify_stripe_signature(payload: bytes, signature_header: str) -> bool:
    if not settings.stripe_webhook_secret:
        return settings.app_env != "production"
    pieces: dict[str, list[str]] = {}
    for part in signature_header.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            pieces.setdefault(key, []).append(value)
    timestamp = pieces.get("t", [""])[0]
    signatures = pieces.get("v1", [])
    if not timestamp or not signatures:
        return False
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(settings.stripe_webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, signature) for signature in signatures)


async def _active_stripe_session_for_transaction(db, transaction_id: ObjectId) -> dict[str, Any] | None:
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
    if record and record.get("providerSessionUrl"):
        return {
            "checkoutUrl": record.get("providerSessionUrl", ""),
            "sessionId": record.get("providerSessionId", ""),
            "paymentRecordId": str(record["_id"]),
            "reused": True,
        }
    return None


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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=stripe_error or "Unable to retrieve Stripe checkout session.")
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
    payment_options = transaction.get("paymentInstructions") or await get_customer_payment_options_for_tenant(tenant_oid)
    normalize_customer_payment_preference("stripe_test", payment_options)
    current_summary = await _calculate_payment_summary(tenant_oid, transaction)
    balance = current_summary["balance"]
    if balance <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction has no remaining balance.")
    active_session = await _active_stripe_session_for_transaction(db, transaction["_id"])
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
        "currency": settings.stripe_currency.upper(),
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
    record["_id"] = (await db.payment_records.insert_one(record)).inserted_id

    payload = {
        "mode": "payment",
        "success_url": _stripe_success_url(settings.stripe_success_path, str(transaction["_id"]), success_url),
        "cancel_url": _stripe_return_url(settings.stripe_cancel_path, str(transaction["_id"]), cancel_url),
        "client_reference_id": str(transaction["_id"]),
        "customer_email": (transaction.get("customerSnapshot") or {}).get("email") or current_user.get("email", ""),
        "metadata[tenantId]": str(tenant_oid),
        "metadata[transactionId]": str(transaction["_id"]),
        "metadata[paymentRecordId]": str(record["_id"]),
        "payment_intent_data[metadata][tenantId]": str(tenant_oid),
        "payment_intent_data[metadata][transactionId]": str(transaction["_id"]),
        "payment_intent_data[metadata][paymentRecordId]": str(record["_id"]),
        "line_items[0][price_data][currency]": settings.stripe_currency.lower(),
        "line_items[0][price_data][product_data][name]": f"{transaction.get('transactionNumber', 'BizXusAI order')} payment",
        "line_items[0][price_data][unit_amount]": str(_stripe_amount_to_minor_units(balance)),
        "line_items[0][quantity]": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=payload,
                auth=(settings.stripe_secret_key, ""),
                headers={"Idempotency-Key": f"bizxusai-checkout-{record['_id']}"},
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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=stripe_error or "Unable to create Stripe checkout session.")

    session = response.json()
    await db.payment_records.update_one(
        {"_id": record["_id"]},
        {"$set": {"providerSessionId": session.get("id", ""), "providerSessionUrl": session.get("url", ""), "referenceNumber": session.get("id", ""), "notes": "Stripe Checkout session is waiting for customer payment.", "updatedAt": datetime.now(timezone.utc)}},
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
    payment_options = transaction.get("paymentInstructions") or await get_customer_payment_options_for_tenant(tenant["_id"])
    normalize_customer_payment_preference("stripe_test", payment_options)
    current_summary = await _calculate_payment_summary(tenant["_id"], transaction)
    balance = current_summary["balance"]
    if balance <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This transaction has no remaining balance.")
    active_session = await _active_stripe_session_for_transaction(db, transaction["_id"])
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
        "currency": settings.stripe_currency.upper(),
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
        "line_items[0][price_data][currency]": settings.stripe_currency.lower(),
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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=stripe_error or "Unable to create Stripe checkout session.")
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


async def mark_stripe_checkout_completed(session: dict[str, Any]) -> dict[str, Any]:
    db = get_database()
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
        await db.payment_records.update_one(
            {"_id": record["_id"]},
            {"$set": {"status": "paid", "amount": paid_amount or record.get("amount", 0), "providerPaymentIntentId": session.get("payment_intent", ""), "referenceNumber": session.get("payment_intent") or session.get("id", ""), "notes": "Stripe Checkout payment completed.", "updatedAt": now}},
        )
        record_id = record["_id"]
    else:
        record = {
            "tenantId": tenant_oid,
            "transactionId": transaction_oid,
            "transactionNumber": transaction.get("transactionNumber", ""),
            "customerSnapshot": transaction.get("customerSnapshot", {}),
            "recordType": "payment",
            "amount": paid_amount,
            "currency": settings.stripe_currency.upper(),
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
    if session.get("payment_status") == "paid" or session.get("status") == "complete":
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
    if session.get("payment_status") == "paid" or session.get("status") == "complete":
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
    if session.get("payment_status") == "paid" or session.get("status") == "complete":
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
    existing = await db.stripe_webhook_events.find_one({"eventId": event_id})
    if existing and existing.get("status") == "processed":
        return {"processed": False, "duplicate": True, "eventType": event_type}
    now = datetime.now(timezone.utc)
    await db.stripe_webhook_events.update_one(
        {"eventId": event_id},
        {
            "$set": {
                "eventType": event_type,
                "tenantId": tenant_oid,
                "transactionId": metadata.get("transactionId", ""),
                "paymentRecordId": metadata.get("paymentRecordId", ""),
                "stripeObjectId": session.get("id", ""),
                "status": "processing",
                "updatedAt": now,
            },
            "$setOnInsert": {"eventId": event_id, "createdAt": now},
        },
        upsert=True,
    )
    try:
        if event_type == "checkout.session.completed":
            data = await mark_stripe_checkout_completed(session)
            await db.stripe_webhook_events.update_one({"eventId": event_id}, {"$set": {"status": "processed", "processedAt": datetime.now(timezone.utc), "error": ""}})
            return {"processed": True, "eventType": event_type, **data}
        await db.stripe_webhook_events.update_one({"eventId": event_id}, {"$set": {"status": "ignored", "processedAt": datetime.now(timezone.utc), "error": ""}})
        return {"processed": False, "eventType": event_type}
    except Exception as exc:
        await db.stripe_webhook_events.update_one({"eventId": event_id}, {"$set": {"status": "failed", "processedAt": datetime.now(timezone.utc), "error": str(exc)}})
        raise
