from __future__ import annotations

from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id
from app.db.mongodb import get_database


def _request_value(requested: Any, key: str, default: Any = None) -> Any:
    if isinstance(requested, dict):
        return requested.get(key, default)
    return getattr(requested, key, default)


def normalize_option_values(options: dict[str, Any] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (options or {}).items():
        clean_key = str(key or "").strip().lower()
        clean_value = str(value or "").strip().lower()
        if clean_key and clean_value:
            normalized[clean_key] = clean_value
    return normalized


def _variant_option_values(variant: dict[str, Any]) -> dict[str, str]:
    return normalize_option_values(variant.get("optionValues") or {})


def _variant_matches_options(variant: dict[str, Any], selected_options: dict[str, Any]) -> bool:
    requested = normalize_option_values(selected_options)
    if not requested:
        return False
    variant_options = _variant_option_values(variant)
    return all(variant_options.get(key) == value for key, value in requested.items())


def active_variants(item: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [(index, variant) for index, variant in enumerate(item.get("variants", [])) if variant.get("isActive", True)]


def resolve_requested_variant(item: dict[str, Any], requested: Any) -> tuple[int | None, dict[str, Any] | None]:
    variants = active_variants(item)
    if not variants:
        return None, None

    selected_index = _request_value(requested, "selectedVariantIndex")
    if selected_index is not None and selected_index != "":
        try:
            selected_index_int = int(selected_index)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid selected variant.")
        for index, variant in variants:
            if index == selected_index_int:
                return index, variant
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected variant is no longer available.")

    variant_sku = str(_request_value(requested, "variantSku", "") or "").strip().lower()
    if variant_sku:
        for index, variant in variants:
            if str(variant.get("sku", "") or "").strip().lower() == variant_sku:
                return index, variant
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected variant SKU is no longer available.")

    selected_options = _request_value(requested, "selectedOptions") or {}
    if selected_options:
        for index, variant in variants:
            if _variant_matches_options(variant, selected_options):
                return index, variant
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected variant options are no longer available.")

    selected_name = str(_request_value(requested, "selectedVariantName", "") or "").strip().lower()
    if selected_name:
        for index, variant in variants:
            if str(variant.get("name", "") or "").strip().lower() == selected_name:
                return index, variant
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected variant is no longer available.")

    default_variant = next(((index, variant) for index, variant in variants if variant.get("isDefault")), None)
    if default_variant:
        return default_variant
    if len(variants) == 1:
        return variants[0]
    return None, None


def is_stock_required(item: dict[str, Any]) -> bool:
    if not item.get("isStockTracked", True):
        return False
    if "stock" not in item and not item.get("variants"):
        return False
    if item.get("isBookable"):
        return False
    if item.get("itemType") in {"service", "digital_product"}:
        return False
    return True


def get_line_availability(item: dict[str, Any], quantity: int, variant: dict[str, Any] | None = None) -> dict[str, Any]:
    quantity = max(1, int(quantity or 1))
    if not is_stock_required(item):
        return {
            "tracked": False,
            "scope": "not_tracked",
            "available": True,
            "availableQuantity": None,
            "requestedQuantity": quantity,
            "message": "Stock is not tracked for this item.",
        }

    if variant:
        total_quantity = float(variant.get("stockQuantity", 0) or 0)
        reserved_quantity = float(variant.get("reservedQuantity", 0) or 0)
        available_quantity = max(0, total_quantity - reserved_quantity)
        return {
            "tracked": True,
            "scope": "variant",
            "available": available_quantity >= quantity,
            "availableQuantity": available_quantity,
            "reservedQuantity": reserved_quantity,
            "requestedQuantity": quantity,
            "message": "Variant stock is available." if available_quantity >= quantity else "Requested variant does not have enough stock.",
        }

    stock = item.get("stock") or {}
    total_quantity = float(stock.get("quantity", 0) or 0)
    reserved_quantity = float(stock.get("reservedQuantity", 0) or 0)
    available_quantity = max(0, total_quantity - reserved_quantity)
    return {
        "tracked": True,
        "scope": "item",
        "available": available_quantity >= quantity,
        "availableQuantity": available_quantity,
        "reservedQuantity": reserved_quantity,
        "requestedQuantity": quantity,
        "message": "Item stock is available." if available_quantity >= quantity else "Requested quantity is not available in stock.",
    }


def build_transaction_line(item: dict[str, Any], requested: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    quantity = int(_request_value(requested, "quantity", 1) or 1)
    if quantity < 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Quantity must be at least 1.")
    quantity = min(quantity, 99)

    variant_index, variant = resolve_requested_variant(item, requested)
    availability = get_line_availability(item, quantity, variant)
    if not availability.get("available", True):
        item_name = item.get("name", "item")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{item_name} is not available in requested quantity. Available: {availability.get('availableQuantity', 0)}.",
        )

    unit_price = float((variant or {}).get("price") or item.get("price", 0) or 0)
    subtotal = unit_price * quantity
    line = {
        "itemId": item["_id"],
        "name": item.get("name", ""),
        "quantity": quantity,
        "unitPrice": unit_price,
        "currency": item.get("currency", "PKR"),
        "subtotal": subtotal,
    }
    if variant:
        line.update(
            {
                "selectedVariantIndex": variant_index,
                "selectedVariantName": variant.get("name", ""),
                "selectedOptions": variant.get("optionValues") or {},
                "variantSku": variant.get("sku", ""),
            }
        )
    return line, availability


async def resolve_requested_order_items(tenant: dict[str, Any], requested_items: list[Any], db: Any | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    if not requested_items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Add at least one item.")

    requested_ids: list[ObjectId] = []
    for requested in requested_items:
        requested_ids.append(parse_object_id(str(_request_value(requested, "itemId", "")), "itemId"))

    unique_ids = list(dict.fromkeys(requested_ids))
    db = db if db is not None else get_database()
    item_map = {
        item["_id"]: item
        async for item in db.items.find(
            {
                "_id": {"$in": unique_ids},
                "tenantId": tenant["_id"],
                "status": "active",
                "$or": [{"isSellable": True}, {"isBookable": True}],
            }
        )
    }

    resolved_items: list[dict[str, Any]] = []
    transaction_items: list[dict[str, Any]] = []
    subtotal = 0.0
    for requested in requested_items:
        item_oid = parse_object_id(str(_request_value(requested, "itemId", "")), "itemId")
        item = item_map.get(item_oid)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more requested items are unavailable.")
        line, availability = build_transaction_line(item, requested)
        line["stockSnapshot"] = availability
        subtotal += float(line.get("subtotal", 0) or 0)
        resolved_items.append(item)
        transaction_items.append(line)

    return resolved_items, transaction_items, subtotal
