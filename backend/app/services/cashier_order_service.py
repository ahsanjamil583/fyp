"""In-store order entry, listing, and receipts for the cashier dashboard.

Cashier orders are ordinary rows in ``transactions`` with ``source: "cashier"``. Nothing
here defines a parallel order model: the same pricing shape, status vocabulary, inventory
transitions, payment records and customer records are used, so the owner's transaction
queue, analytics, reports and customer history pick these orders up with no extra work.

What is specific to a counter sale:

* payment is taken at the till, so a paid order is created ``completed`` and its stock is
  deducted rather than reserved;
* an item that is not in the catalog can be typed in by hand, and such a line never
  touches inventory because there is nothing to move;
* the receipt is addressed by an unguessable token rather than by the transaction's
  ObjectId, so a printed or shared receipt link exposes no database identifier.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.db.mongodb import get_database
from app.services.business_notification_service import create_business_notification
from app.services.cashier_service import get_cashier_context, normalize_cashier_permissions
from app.services.custom_field_service import validate_custom_values_for_tenant_oid
from app.services.customer_service import sync_customer_stats_for_transaction
from app.services.inventory_service import deduct_transaction_stock, reserve_transaction_stock
from app.services.localization_service import normalize_optional_email, normalize_optional_pk_phone_or_blank
from app.services.order_validation_service import normalize_notes
from app.services.smart_order_service import build_transaction_line
from app.services.transaction_number_service import generate_transaction_number

CASHIER_SOURCE = "cashier"

# What the till can take. These are deliberately not the customer-facing gateway codes:
# nothing is redirected anywhere, the cashier is recording money that already changed
# hands at the counter.
CASHIER_PAYMENT_METHODS = {
    "cash": "Cash",
    "card": "Card",
    "jazzcash": "JazzCash",
    "easypaisa": "Easypaisa",
    "bank_transfer": "Bank transfer",
    "unpaid": "Unpaid / pending",
}

CASHIER_SERVICE_TYPES = {
    "in_store": {"label": "In-store", "fulfillment": "none"},
    "dine_in": {"label": "Dine-in", "fulfillment": "none"},
    "takeaway": {"label": "Takeaway", "fulfillment": "none"},
    "pickup": {"label": "Pickup", "fulfillment": "pickup"},
    "delivery": {"label": "Delivery", "fulfillment": "delivery"},
}

MAX_CASHIER_ORDER_LINES = 60


def cashier_payment_methods() -> list[dict[str, str]]:
    return [{"code": code, "label": label} for code, label in CASHIER_PAYMENT_METHODS.items()]


def cashier_service_types() -> list[dict[str, str]]:
    return [{"code": code, "label": config["label"]} for code, config in CASHIER_SERVICE_TYPES.items()]


def _money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _normalize_payment_method(value: str | None) -> str:
    normalized = str(value or "cash").strip().lower().replace(" ", "_")
    if normalized not in CASHIER_PAYMENT_METHODS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select a valid payment method.")
    return normalized


def _normalize_service_type(value: str | None) -> str:
    normalized = str(value or "in_store").strip().lower().replace("-", "_")
    if normalized not in CASHIER_SERVICE_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select a valid order type.")
    return normalized


def _build_fulfillment(service_type: str, address: dict | None) -> dict:
    """Counter sales bypass the category fulfillment rules on purpose.

    Those rules describe what a *customer* may request on the public site. A cashier
    standing at the till is the business itself, and refusing to record a walk-in sale
    because the business category has delivery switched off would be nonsense.
    """
    fulfillment_type = CASHIER_SERVICE_TYPES[service_type]["fulfillment"]
    raw = address or {}
    normalized_address = {
        "line1": str(raw.get("line1") or raw.get("addressLine1") or raw.get("street") or "").strip()[:200],
        "city": str(raw.get("city") or "").strip()[:80],
    }
    if fulfillment_type == "delivery" and (not normalized_address["line1"] or not normalized_address["city"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Delivery orders need an address line and a city.",
        )
    if fulfillment_type != "delivery":
        normalized_address = {}
    return {"type": fulfillment_type, "address": normalized_address, "serviceType": service_type}


def _compute_pricing(subtotal: float, payload, permissions: dict) -> dict:
    discount_value = _money(getattr(payload, "discountValue", 0))
    if discount_value and not permissions.get("canApplyDiscount", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This cashier is not allowed to apply discounts.")

    discount_type = str(getattr(payload, "discountType", "amount") or "amount").strip().lower()
    if discount_type not in {"amount", "percent"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Discount type must be amount or percent.")
    if discount_type == "percent":
        if discount_value > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Discount percent cannot exceed 100.")
        discount = _money(subtotal * discount_value / 100)
    else:
        discount = _money(discount_value)
    if discount > subtotal:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Discount cannot be larger than the subtotal.")

    taxed_base = _money(subtotal - discount)
    tax_type = str(getattr(payload, "taxType", "amount") or "amount").strip().lower()
    if tax_type not in {"amount", "percent"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tax type must be amount or percent.")
    tax_value = _money(getattr(payload, "taxValue", 0))
    if tax_type == "percent":
        if tax_value > 100:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tax percent cannot exceed 100.")
        tax = _money(taxed_base * tax_value / 100)
    else:
        tax = tax_value

    service_charge = _money(getattr(payload, "serviceCharge", 0))
    delivery_fee = _money(getattr(payload, "deliveryFee", 0))
    total = _money(taxed_base + tax + service_charge + delivery_fee)
    return {
        "subtotal": _money(subtotal),
        "discount": discount,
        "discountType": discount_type,
        "discountValue": discount_value,
        "tax": tax,
        "taxType": tax_type,
        "taxValue": tax_value,
        "serviceCharge": service_charge,
        "deliveryFee": delivery_fee,
        "total": total,
    }


async def _resolve_cashier_lines(tenant_oid: ObjectId, requested_items: list, permissions: dict) -> tuple[list[dict], float, list[dict]]:
    """Turn the entry form's rows into transaction lines.

    Catalog lines reuse ``build_transaction_line`` so pricing, variant resolution and the
    stock check behave exactly as they do for a customer order. Manual lines are marked
    ``isCustomItem`` and carry no ``itemId``, which is what keeps inventory out of them.
    """
    db = get_database()
    if not requested_items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Add at least one item to the order.")
    if len(requested_items) > MAX_CASHIER_ORDER_LINES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="An order can hold at most 60 lines.")

    lines: list[dict] = []
    warnings: list[dict] = []
    subtotal = 0.0

    for index, requested in enumerate(requested_items):
        item_id = str(getattr(requested, "itemId", "") or "").strip()
        quantity = int(getattr(requested, "quantity", 1) or 1)

        if not item_id:
            if not permissions.get("canAddCustomItems", True):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This cashier is not allowed to add manual items.")
            name = str(getattr(requested, "name", "") or "").strip()
            unit_price = getattr(requested, "unitPrice", None)
            if len(name) < 2:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Line {index + 1}: a manual item needs a name.")
            if unit_price is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Line {index + 1}: a manual item needs a unit price.")
            line_subtotal = _money(float(unit_price) * quantity)
            lines.append(
                {
                    "itemId": None,
                    "name": name[:200],
                    "quantity": quantity,
                    "unitPrice": _money(unit_price),
                    "currency": "PKR",
                    "subtotal": line_subtotal,
                    "isCustomItem": True,
                    "stockSnapshot": {"tracked": False, "scope": "not_tracked", "available": True, "message": "Manual item, not tracked in inventory."},
                }
            )
            subtotal += line_subtotal
            continue

        item = await db.items.find_one(
            {
                "_id": parse_object_id(item_id, "itemId"),
                "tenantId": tenant_oid,
                "status": "active",
            }
        )
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Line {index + 1}: that catalog item is no longer available.")

        line, availability = build_transaction_line(item, requested)
        line["stockSnapshot"] = availability
        line["isCustomItem"] = False
        if availability.get("tracked") and availability.get("availableQuantity") is not None:
            remaining = float(availability["availableQuantity"]) - quantity
            if remaining <= 0:
                warnings.append({"itemName": item.get("name", ""), "message": f"{item.get('name', 'Item')} will be out of stock after this sale."})
        subtotal += float(line.get("subtotal", 0) or 0)
        lines.append(line)

    return lines, _money(subtotal), warnings


def cashier_order_view(transaction: dict) -> dict:
    """Cashier-facing projection.

    Internal workflow fields (inventory claims, internal notes, status history, the raw
    transaction id) are dropped: a till operator has no use for them, and a receipt view
    must not leak them either.
    """
    fields = {
        "transactionNumber", "transactionType", "source", "status", "items", "pricing",
        "paymentStatus", "paymentSummary", "customerSnapshot", "fulfillment", "notes",
        "createdAt", "updatedAt", "receiptToken", "cashier", "payment",
    }
    # ``_id`` is deliberately absent: the receipt token is the only handle the cashier
    # workspace uses, so a printed or forwarded receipt carries no database identifier.
    data = serialize_document({key: value for key, value in transaction.items() if key in fields}) or {}
    for line in data.get("items", []):
        line.pop("costPrice", None)
        line.pop("stockSnapshot", None)
        line.pop("itemId", None)
    cashier_block = data.get("cashier") or {}
    cashier_block.pop("cashierId", None)
    cashier_block.pop("userId", None)
    data["cashier"] = cashier_block
    return data


async def create_cashier_order(account: dict, payload) -> dict:
    db = get_database()
    cashier, tenant = await get_cashier_context(account)
    tenant_oid = tenant["_id"]
    permissions = normalize_cashier_permissions(cashier.get("permissions"))

    lines, subtotal, warnings = await _resolve_cashier_lines(tenant_oid, payload.items, permissions)
    pricing = _compute_pricing(subtotal, payload, permissions)
    payment_method = _normalize_payment_method(payload.paymentMethod)
    service_type = _normalize_service_type(payload.serviceType)
    fulfillment = _build_fulfillment(service_type, payload.address)

    custom_fields = await validate_custom_values_for_tenant_oid(tenant_oid, "transactions", "transaction", payload.customFields or {})
    if not custom_fields["valid"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=custom_fields["errors"])

    is_paid = payment_method != "unpaid"
    order_status = "completed" if is_paid else "pending"
    now = datetime.now(timezone.utc)
    customer_name = str(payload.customerName or "").strip()[:120] or "Walk-in customer"
    customer_phone = normalize_optional_pk_phone_or_blank(payload.customerPhone or "")
    customer_email = normalize_optional_email(payload.customerEmail or "")

    transaction = {
        "tenantId": tenant_oid,
        "branchId": None,
        "customerId": None,
        "customerUserId": None,
        "customerProfileId": None,
        "transactionType": "order",
        "transactionNumber": await generate_transaction_number(tenant_oid, "order"),
        "receiptToken": secrets.token_urlsafe(18),
        "source": CASHIER_SOURCE,
        "status": order_status,
        "items": lines,
        "pricing": pricing,
        "paymentStatus": "paid" if is_paid else "unpaid",
        "paymentSummary": {
            "total": pricing["total"],
            "paid": pricing["total"] if is_paid else 0,
            "cod": 0,
            "pending": 0,
            "rejected": 0,
            "refunded": 0,
            "balance": 0 if is_paid else pricing["total"],
        },
        "payment": {
            "method": payment_method,
            "methodLabel": CASHIER_PAYMENT_METHODS[payment_method],
            "amountReceived": _money(payload.amountReceived) if payload.amountReceived is not None else (pricing["total"] if is_paid else 0),
            "changeDue": 0.0,
        },
        "fulfillment": fulfillment,
        "customerSnapshot": {"name": customer_name, "phone": customer_phone, "email": customer_email},
        "notes": normalize_notes(payload.notes),
        "internalNotes": "",
        "customFields": custom_fields["values"],
        "cashier": {
            "cashierId": cashier["_id"],
            "userId": account["_id"],
            "name": cashier.get("fullName", account.get("fullName", "")),
            "employeeCode": cashier.get("employeeCode", ""),
        },
        "statusHistory": [
            {
                "field": "status",
                "from": None,
                "to": order_status,
                "note": f"Created at the counter by {cashier.get('fullName', 'cashier')}.",
                "changedAt": now,
                "changedByUserId": account["_id"],
            }
        ],
        "createdBy": account["_id"],
        "createdAt": now,
        "updatedAt": now,
    }
    if is_paid and payload.amountReceived is not None:
        transaction["payment"]["changeDue"] = max(0.0, _money(float(payload.amountReceived) - pricing["total"]))

    transaction["_id"] = (await db.transactions.insert_one(transaction)).inserted_id
    try:
        # A paid counter sale leaves the shop with the goods, so the stock is gone rather
        # than reserved. An unpaid one is a held order and only reserves.
        transaction = (
            await deduct_transaction_stock(transaction, account["_id"])
            if is_paid
            else await reserve_transaction_stock(transaction, account["_id"])
        )
    except Exception:
        await db.transactions.delete_one({"_id": transaction["_id"]})
        raise

    if is_paid:
        await db.payment_records.insert_one(
            {
                "tenantId": tenant_oid,
                "transactionId": transaction["_id"],
                "transactionNumber": transaction.get("transactionNumber", ""),
                "customerSnapshot": transaction.get("customerSnapshot", {}),
                "recordType": "payment",
                "amount": pricing["total"],
                "currency": (lines[0].get("currency") if lines else "PKR") or "PKR",
                "method": payment_method,
                "methodLabel": CASHIER_PAYMENT_METHODS[payment_method],
                "status": "paid",
                "referenceNumber": "",
                "screenshotUrl": "",
                "notes": f"Counter payment taken by {cashier.get('fullName', 'cashier')}.",
                "verification": {
                    "requiresOwnerApproval": False,
                    "verifiedByUserId": account["_id"],
                    "verifiedAt": now,
                },
                "source": CASHIER_SOURCE,
                "createdBy": account["_id"],
                "createdAt": now,
                "updatedAt": now,
            }
        )

    if customer_phone or customer_email:
        await sync_customer_stats_for_transaction(tenant, transaction)
        transaction = await db.transactions.find_one({"_id": transaction["_id"]}) or transaction

    await create_business_notification(
        tenant_oid,
        "order_alert",
        f"Counter sale {transaction['transactionNumber']}",
        f"{cashier.get('fullName', 'A cashier')} recorded a {CASHIER_PAYMENT_METHODS[payment_method].lower()} order of {pricing['total']:g}.",
        priority="medium",
        metadata={
            "transactionId": str(transaction["_id"]),
            "transactionNumber": transaction["transactionNumber"],
            "transactionType": "order",
            "source": CASHIER_SOURCE,
            "cashierName": cashier.get("fullName", ""),
            "tenantSlug": tenant.get("slug", ""),
        },
    )
    return {"order": cashier_order_view(transaction), "warnings": warnings}


def _order_scope_query(cashier: dict, tenant_oid: ObjectId) -> dict:
    """Which cashier orders this cashier may read.

    Their own always; every cashier's only when the owner has granted it.
    """
    query: dict = {"tenantId": tenant_oid, "source": CASHIER_SOURCE}
    permissions = normalize_cashier_permissions(cashier.get("permissions"))
    if not permissions.get("canViewAllCashierOrders"):
        query["cashier.cashierId"] = cashier["_id"]
    return query


async def list_cashier_orders(account: dict, search: str = "", status_filter: str | None = None, page: int = 1, limit: int = 20) -> dict:
    db = get_database()
    cashier, tenant = await get_cashier_context(account)
    page = max(page, 1)
    limit = min(max(limit, 1), 100)

    query = _order_scope_query(cashier, tenant["_id"])
    if status_filter:
        query["status"] = str(status_filter).strip().lower()
    if search:
        pattern = re.escape(str(search)[:120])
        query["$or"] = [
            {"transactionNumber": {"$regex": pattern, "$options": "i"}},
            {"customerSnapshot.name": {"$regex": pattern, "$options": "i"}},
            {"customerSnapshot.phone": {"$regex": pattern, "$options": "i"}},
        ]

    total = await db.transactions.count_documents(query)
    cursor = db.transactions.find(query).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
    items = [cashier_order_view(row) async for row in cursor]
    return {
        "items": items,
        "pagination": {"page": page, "limit": limit, "total": total, "totalPages": (total + limit - 1) // limit},
    }


async def get_cashier_order(account: dict, receipt_token: str) -> dict:
    db = get_database()
    cashier, tenant = await get_cashier_context(account)
    token = str(receipt_token or "").strip()
    if not token or len(token) > 120:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")
    order = await db.transactions.find_one({**_order_scope_query(cashier, tenant["_id"]), "receiptToken": token})
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")
    return cashier_order_view(order)


def receipt_business_block(tenant: dict) -> dict:
    contact = tenant.get("contact") or {}
    address = tenant.get("address") or {}
    logo = tenant.get("logo") or {}
    website_settings = tenant.get("websiteSettings") or {}
    return {
        "name": tenant.get("name", ""),
        "logoUrl": logo.get("url", ""),
        "phone": contact.get("phone", "") or contact.get("whatsapp", ""),
        "email": contact.get("email", ""),
        "addressLine": ", ".join(part for part in [address.get("line1", ""), address.get("city", ""), address.get("province", "")] if part),
        "currency": ((tenant.get("settings") or {}).get("currency")) or "PKR",
        "footerMessage": str(website_settings.get("receiptFooter") or "Thank you for your purchase.").strip()[:200],
    }


async def get_cashier_receipt(account: dict, receipt_token: str) -> dict:
    cashier, tenant = await get_cashier_context(account)
    order = await get_cashier_order(account, receipt_token)
    return {
        "business": receipt_business_block(tenant),
        "order": order,
        "servedBy": order.get("cashier", {}).get("name") or cashier.get("fullName", ""),
    }


async def get_cashier_dashboard(account: dict) -> dict:
    db = get_database()
    cashier, tenant = await get_cashier_context(account)
    tenant_oid = tenant["_id"]
    scope = _order_scope_query(cashier, tenant_oid)

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_scope = {**scope, "createdAt": {"$gte": day_start}}

    today_orders = await db.transactions.count_documents(today_scope)
    pending_orders = await db.transactions.count_documents({**scope, "status": {"$in": ["pending", "confirmed", "processing", "ready"]}})
    unpaid_orders = await db.transactions.count_documents({**scope, "paymentStatus": {"$in": ["unpaid", "partially_paid"]}})
    completed_orders = await db.transactions.count_documents({**scope, "status": "completed"})

    sales_rows = await db.transactions.aggregate(
        [
            {"$match": {**today_scope, "status": {"$ne": "cancelled"}}},
            {"$group": {"_id": None, "total": {"$sum": "$pricing.total"}, "count": {"$sum": 1}}},
        ]
    ).to_list(length=1)
    today_sales = _money(sales_rows[0]["total"]) if sales_rows else 0.0

    week_start = day_start - timedelta(days=6)
    trend_rows = await db.transactions.aggregate(
        [
            {"$match": {**scope, "createdAt": {"$gte": week_start}, "status": {"$ne": "cancelled"}}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}},
                    "total": {"$sum": "$pricing.total"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
    ).to_list(length=None)

    recent_cursor = db.transactions.find(scope).sort("createdAt", -1).limit(8)
    recent = [cashier_order_view(row) async for row in recent_cursor]

    permissions = normalize_cashier_permissions(cashier.get("permissions"))
    return {
        "cashier": {
            "name": cashier.get("fullName", account.get("fullName", "")),
            "employeeCode": cashier.get("employeeCode", ""),
            "permissions": permissions,
        },
        "business": {
            "name": tenant.get("name", ""),
            "currency": ((tenant.get("settings") or {}).get("currency")) or "PKR",
            "logoUrl": (tenant.get("logo") or {}).get("url", ""),
        },
        "today": {
            "sales": today_sales,
            "orders": today_orders,
        },
        "counters": {
            "pendingOrders": pending_orders,
            "unpaidOrders": unpaid_orders,
            "completedOrders": completed_orders,
        },
        "trend": [{"date": row["_id"], "total": _money(row["total"]), "count": row["count"]} for row in trend_rows],
        "recentOrders": recent,
        "paymentMethods": cashier_payment_methods(),
        "serviceTypes": cashier_service_types(),
    }


async def list_cashier_catalog(account: dict, search: str = "", limit: int = 40) -> list[dict]:
    """Catalog lookup for the order screen: only what a receipt line needs."""
    db = get_database()
    _, tenant = await get_cashier_context(account)
    limit = min(max(int(limit or 40), 1), 100)
    query: dict = {
        "tenantId": tenant["_id"],
        "status": "active",
        "$or": [{"isSellable": True}, {"isBookable": True}],
    }
    if search:
        pattern = re.escape(str(search)[:120])
        query["$and"] = [
            {
                "$or": [
                    {"name": {"$regex": pattern, "$options": "i"}},
                    {"sku": {"$regex": pattern, "$options": "i"}},
                    {"tags": {"$regex": pattern, "$options": "i"}},
                ]
            }
        ]

    cursor = db.items.find(query).sort("name", 1).limit(limit)
    results = []
    async for item in cursor:
        stock = item.get("stock") or {}
        results.append(
            {
                "id": str(item["_id"]),
                "name": item.get("name", ""),
                "sku": item.get("sku", ""),
                "price": _money(item.get("price")),
                "currency": item.get("currency", "PKR"),
                "unit": item.get("unit", "piece"),
                "isStockTracked": bool(item.get("isStockTracked", True)),
                "availableQuantity": max(0.0, float(stock.get("quantity", 0) or 0) - float(stock.get("reservedQuantity", 0) or 0)),
                "variants": [
                    {
                        "index": index,
                        "name": variant.get("name", ""),
                        "sku": variant.get("sku", ""),
                        "price": _money(variant.get("price") or item.get("price")),
                        "availableQuantity": max(0.0, float(variant.get("stockQuantity", 0) or 0) - float(variant.get("reservedQuantity", 0) or 0)),
                        "optionValues": variant.get("optionValues") or {},
                    }
                    for index, variant in enumerate(item.get("variants") or [])
                    if variant.get("isActive", True)
                ],
            }
        )
    return results
