"""Cart line identity, variant resolution, and pricing.

Pure functions, deliberately kept below the service layer: both the HTTP cart and the
agent's basket need them, and putting them in either one would have made the other
import a service it has no other business knowing about.

One definition of "the same line" lives here, so the cart page and the chat can never
disagree about whether two variants are one row or two.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.services.smart_order_service import resolve_requested_variant


def cart_line_key(line: dict) -> tuple:
    """Identity of a cart line: the item plus the exact variant chosen.

    Used for merging a repeat "add". Two variants of one item are deliberately two
    lines, because they have different prices and different stock.
    """
    variant_index = line.get("selectedVariantIndex")
    variant_key = int(variant_index) if variant_index not in (None, "") else None
    return (str(line.get("itemId")), variant_key, str(line.get("variantSku", "") or "").strip().lower())


def find_cart_line(cart: dict, reference: str) -> dict | None:
    """Locate a line by its lineId, falling back to itemId for pre-lineId carts."""
    reference = str(reference or "").strip()
    if not reference:
        return None
    lines = cart.get("items", [])
    for line in lines:
        if str(line.get("lineId", "")) == reference:
            return line
    for line in lines:
        if str(line.get("itemId")) == reference:
            return line
    return None


def build_cart_line(item: dict, payload) -> dict:
    """Turn an add-to-cart request into a stored line, validating the variant.

    Variant resolution goes through the same helper the order builder uses, so a
    variant that cannot be honoured is refused here rather than silently swapped for
    the default at checkout.
    """
    variant_index, variant = resolve_requested_variant(item, payload)
    line = {
        "lineId": uuid4().hex,
        "itemId": item["_id"],
        "quantity": int(payload.quantity),
        "selectedVariantIndex": variant_index,
        "selectedVariantName": (variant or {}).get("name", "") if variant else "",
        "selectedOptions": (variant or {}).get("optionValues") or {},
        "variantSku": (variant or {}).get("sku", "") if variant else "",
    }
    return line


def cart_line_unit_price(item: dict | None, line: dict) -> float:
    """What this line costs each, honouring the chosen variant."""
    if not item:
        return 0.0
    variant_index = line.get("selectedVariantIndex")
    variants = item.get("variants") or []
    if variant_index not in (None, "") and 0 <= int(variant_index) < len(variants):
        return float(variants[int(variant_index)].get("price") or item.get("price", 0) or 0)
    return float(item.get("price", 0) or 0)
