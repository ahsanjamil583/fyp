"""The order receipt: one document per order, reachable by an unguessable token.

There were already two receipt artefacts before this, and adding a third would have been
the wrong move:

* ``payment_service._build_payment_receipt_html`` is proof that **one payment** was
  taken. An order paid in two instalments has two of them. It stays exactly as it is.
* the cashier's thermal slip is proof of a **counter sale**, rendered in React and
  printed at the till. It stays as it is too.

What was missing is proof of **the order itself** for orders placed online, which is what
a customer wants in their inbox. That is this module, and the cashier's ``receiptToken``
scheme is reused rather than reinvented so there is one way to address a receipt.

The token is the only key. It is unguessable, it is not the order's ObjectId, and the
lookup is by token alone - so a receipt link can be emailed or sent over WhatsApp without
the recipient needing an account, and without the URL leaking a database identifier.
"""

from __future__ import annotations

import secrets
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.receipt_format import format_receipt_date, format_receipt_money, receipt_text
from app.db.mongodb import get_database

RECEIPT_TOKEN_BYTES = 18


async def ensure_receipt_token(transaction: dict[str, Any]) -> str:
    """Give an order a receipt token, or return the one it already has.

    Cashier orders are minted with a token at creation; online orders were not, so this
    backfills lazily. Written with a filter on the token still being absent, so two
    concurrent requests cannot mint two tokens for the same order.
    """
    existing = str(transaction.get("receiptToken") or "").strip()
    if existing:
        return existing

    db = get_database()
    token = secrets.token_urlsafe(RECEIPT_TOKEN_BYTES)
    result = await db.transactions.update_one(
        {"_id": transaction["_id"], "receiptToken": {"$exists": False}},
        {"$set": {"receiptToken": token}},
    )
    if result.modified_count:
        transaction["receiptToken"] = token
        return token

    # Someone else won the race, or the field existed as an empty value. Re-read.
    refreshed = await db.transactions.find_one({"_id": transaction["_id"]}, {"receiptToken": 1})
    current = str((refreshed or {}).get("receiptToken") or "").strip()
    if current:
        transaction["receiptToken"] = current
        return current

    await db.transactions.update_one({"_id": transaction["_id"]}, {"$set": {"receiptToken": token}})
    transaction["receiptToken"] = token
    return token


def _line_rows(transaction: dict[str, Any], currency: str) -> str:
    rows = ""
    for line in transaction.get("items") or []:
        options = line.get("selectedOptions") or {}
        option_text = ", ".join(f"{key}: {value}" for key, value in options.items() if value) if isinstance(options, dict) else ""
        variant = receipt_text(line.get("selectedVariantName"), "")
        detail = " / ".join(part for part in [variant, receipt_text(option_text, "")] if part and part != "-")
        rows += f"""
          <tr>
            <td>
              <strong>{receipt_text(line.get('name'), 'Item')}</strong>
              {f'<div class="muted">{detail}</div>' if detail else ''}
            </td>
            <td class="center">{receipt_text(line.get('quantity'), '1')}</td>
            <td class="right">{format_receipt_money(line.get('unitPrice') or 0, currency)}</td>
            <td class="right">{format_receipt_money(line.get('subtotal') or 0, currency)}</td>
          </tr>"""
    return rows or '<tr><td colspan="4" class="muted">No items recorded.</td></tr>'


def _totals_rows(pricing: dict[str, Any], currency: str) -> str:
    rows = ""
    for label, key in (("Discount", "discount"), ("Tax", "tax"), ("Service charge", "serviceCharge"), ("Delivery", "deliveryFee")):
        value = float(pricing.get(key) or 0)
        if value:
            prefix = "- " if key == "discount" else ""
            rows += f'<tr><td>{label}</td><td class="right">{prefix}{format_receipt_money(value, currency)}</td></tr>'
    return rows


def build_order_receipt_html(tenant: dict[str, Any], transaction: dict[str, Any]) -> str:
    """Render the receipt.

    Deliberately self-contained HTML with inline styles and a print stylesheet: it is
    opened from an email or a WhatsApp link, where no stylesheet of ours will load, and
    it must print cleanly on whatever the customer has.
    """
    pricing = transaction.get("pricing") or {}
    currency = pricing.get("currency") or (transaction.get("items") or [{}])[0].get("currency") or "PKR"
    customer = transaction.get("customerSnapshot") or {}
    contact = tenant.get("contact") or {}
    address = tenant.get("address") or {}
    fulfillment = transaction.get("fulfillment") or {}
    payment_status = str(transaction.get("paymentStatus", "unpaid"))
    is_paid = payment_status in {"paid", "cod"}

    business_line = ", ".join(
        part for part in [receipt_text(address.get("line1"), ""), receipt_text(address.get("city"), "")]
        if part and part != "-"
    )
    delivery_address = fulfillment.get("address") or {}
    delivery_line = ", ".join(
        part for part in [receipt_text(delivery_address.get("line1"), ""), receipt_text(delivery_address.get("city"), "")]
        if part and part != "-"
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Receipt {receipt_text(transaction.get('transactionNumber'), '')}</title>
<style>
  body {{ margin:0; background:#eef3f9; font-family:Arial,Helvetica,sans-serif; color:#172033; }}
  main {{ max-width:640px; margin:32px auto; padding:0 16px; }}
  .card {{ background:#fff; border:1px solid #d7e2ef; border-radius:18px; overflow:hidden; }}
  .head {{ background:#172033; color:#fff; padding:24px 28px; }}
  .head h1 {{ margin:6px 0 2px; font-size:24px; }}
  .head p {{ margin:0; color:#dbeafe; font-size:14px; }}
  .eyebrow {{ font-size:11px; letter-spacing:.2em; text-transform:uppercase; color:#93c5fd; font-weight:800; }}
  .body {{ padding:24px 28px; }}
  dl {{ display:grid; grid-template-columns:auto 1fr; gap:6px 16px; font-size:14px; margin:0 0 20px; }}
  dt {{ color:#64748b; }} dd {{ margin:0; text-align:right; font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:#64748b;
       border-bottom:1px solid #e2e8f0; padding:0 0 8px; }}
  td {{ padding:10px 0; border-bottom:1px solid #f1f5f9; vertical-align:top; }}
  .center {{ text-align:center; }} .right {{ text-align:right; white-space:nowrap; }}
  .muted {{ color:#64748b; font-size:12px; margin-top:2px; }}
  .totals {{ margin-top:16px; }} .totals td {{ border:0; padding:4px 0; }}
  .grand {{ font-size:20px; font-weight:800; border-top:2px solid #172033 !important; padding-top:10px !important; }}
  .pill {{ display:inline-block; padding:6px 14px; border-radius:999px; font-size:12px; font-weight:800;
           text-transform:uppercase; letter-spacing:.06em; }}
  .paid {{ background:#ecfdf5; color:#065f46; }} .due {{ background:#fff7ed; color:#9a3412; }}
  .foot {{ padding:18px 28px; border-top:1px solid #e2e8f0; color:#64748b; font-size:12px; }}
  @media print {{
    body {{ background:#fff; }}
    main {{ margin:0; padding:0; max-width:100%; }}
    .card {{ border:0; border-radius:0; }}
    .head {{ background:#fff; color:#172033; border-bottom:2px solid #172033; }}
    .head p, .eyebrow {{ color:#475569; }}
    .no-print {{ display:none !important; }}
  }}
</style></head>
<body><main><div class="card">
  <div class="head">
    <div class="eyebrow">Receipt</div>
    <h1>{receipt_text(tenant.get('name'), 'BizXusAI Business')}</h1>
    <p>{business_line or receipt_text(contact.get('phone'), '')}</p>
  </div>
  <div class="body">
    <dl>
      <dt>Order</dt><dd>{receipt_text(transaction.get('transactionNumber'), '-')}</dd>
      <dt>Date</dt><dd>{format_receipt_date(transaction.get('createdAt'))}</dd>
      <dt>Customer</dt><dd>{receipt_text(customer.get('name'), 'Guest')}</dd>
      {f"<dt>Phone</dt><dd>{receipt_text(customer.get('phone'), '')}</dd>" if customer.get('phone') else ''}
      <dt>Status</dt><dd>{receipt_text(str(transaction.get('status', '')).replace('_', ' ').title(), '-')}</dd>
      {f"<dt>Deliver to</dt><dd>{delivery_line}</dd>" if delivery_line else ''}
    </dl>

    <table>
      <thead><tr><th>Item</th><th class="center">Qty</th><th class="right">Unit</th><th class="right">Amount</th></tr></thead>
      <tbody>{_line_rows(transaction, currency)}</tbody>
    </table>

    <table class="totals">
      <tr><td>Subtotal</td><td class="right">{format_receipt_money(pricing.get('subtotal') or 0, currency)}</td></tr>
      {_totals_rows(pricing, currency)}
      <tr><td class="grand">Total</td><td class="right grand">{format_receipt_money(pricing.get('total') or 0, currency)}</td></tr>
    </table>

    <p style="margin-top:18px;">
      <span class="pill {'paid' if is_paid else 'due'}">
        {'Paid' if is_paid else receipt_text(payment_status.replace('_', ' ').title(), 'Payment pending')}
      </span>
    </p>
    {f'<p class="muted">{receipt_text(transaction.get("notes"), "")}</p>' if transaction.get('notes') else ''}
  </div>
  <div class="foot">
    Thank you for your order. Keep this receipt for your records.
    {f"<br/>Questions? Contact {receipt_text(contact.get('phone'), '')}." if contact.get('phone') else ''}
  </div>
</div></main></body></html>"""


async def get_order_receipt_html_by_token(token: str) -> str:
    """Look an order up by receipt token alone.

    The token is the credential, which is what lets an emailed link work for a guest who
    has no account. It is 24 characters of URL-safe randomness and is never derived from
    the order id, so possession of a link grants nothing beyond that one receipt.
    """
    cleaned = str(token or "").strip()
    if not cleaned or len(cleaned) > 120:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")

    db = get_database()
    transaction = await db.transactions.find_one({"receiptToken": cleaned})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")

    tenant = await db.tenants.find_one({"_id": transaction["tenantId"]})
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")
    return build_order_receipt_html(tenant, transaction)


async def get_order_receipt_for_customer(order_id: str, current_user: dict) -> dict[str, Any]:
    """The receipt link for an order the signed-in customer owns."""
    db = get_database()
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid orderId.")
    transaction = await db.transactions.find_one({"_id": ObjectId(order_id), "customerUserId": current_user["_id"]})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    token = await ensure_receipt_token(transaction)
    return {"receiptToken": token, "transactionNumber": transaction.get("transactionNumber", "")}
