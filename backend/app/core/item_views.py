"""Customer-facing projections of catalog data.

Item documents carry information the business does not want published: what it paid
for stock, and exactly how much of it is on hand. Public website, customer portal,
and AI chat responses all pass through here so that data cannot escape by way of a
new endpoint reusing ``serialize_document`` directly.
"""

from __future__ import annotations

from typing import Any

from app.core.object_ids import serialize_document

# Never rendered to a customer. costPrice reveals margin; supplier notes and internal
# fields would be equally sensitive if they are added later.
OWNER_ONLY_ITEM_FIELDS = ("costPrice",)

# Exact counts let a competitor track sales volume, so customers see a band instead.
LOW_STOCK_BAND = 5

STOCK_IN = "in_stock"
STOCK_LOW = "low_stock"
STOCK_OUT = "out_of_stock"
STOCK_UNTRACKED = "not_tracked"


def _available_quantity(total: Any, reserved: Any) -> float:
    return max(0.0, float(total or 0) - float(reserved or 0))


def coarse_stock_status(available: float, low_threshold: Any = 0) -> str:
    if available <= 0:
        return STOCK_OUT
    if available <= max(float(low_threshold or 0), LOW_STOCK_BAND):
        return STOCK_LOW
    return STOCK_IN


def customer_stock_view(item: dict[str, Any]) -> dict[str, Any]:
    """Availability band for an item, with no quantities."""
    if not item.get("isStockTracked"):
        return {"status": STOCK_UNTRACKED, "tracked": False, "inStock": True}
    stock = item.get("stock") or {}
    available = _available_quantity(stock.get("quantity"), stock.get("reservedQuantity"))
    status = coarse_stock_status(available, stock.get("lowStockThreshold"))
    return {"status": status, "tracked": True, "inStock": status != STOCK_OUT}


def _customer_variant_view(variant: dict[str, Any], item_tracked: bool) -> dict[str, Any]:
    data = dict(variant)
    total = data.pop("stockQuantity", None)
    reserved = data.pop("reservedQuantity", None)
    data.pop("lowStockThreshold", None)
    data.pop("costPrice", None)
    if item_tracked:
        available = _available_quantity(total, reserved)
        data["stockStatus"] = coarse_stock_status(available, variant.get("lowStockThreshold"))
    else:
        data["stockStatus"] = STOCK_UNTRACKED
    return data


def customer_item_view(item: dict[str, Any] | None) -> dict[str, Any]:
    """Serialize an item for a customer or anonymous visitor."""
    data = serialize_document(item) or {}
    if not data:
        return data

    for field in OWNER_ONLY_ITEM_FIELDS:
        data.pop(field, None)

    tracked = bool(data.get("isStockTracked"))
    data["stock"] = customer_stock_view(data)
    data["variants"] = [_customer_variant_view(v, tracked) for v in (data.get("variants") or [])]
    return data


def customer_stock_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Strip quantities from a draft-order line's availability snapshot."""
    if not snapshot:
        return {}
    data = dict(snapshot)
    available = data.pop("availableQuantity", None)
    data.pop("reservedQuantity", None)
    if data.get("tracked"):
        data["status"] = coarse_stock_status(float(available or 0), 0)
    else:
        data["status"] = STOCK_UNTRACKED
    return data
