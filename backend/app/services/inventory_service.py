from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.db.mongodb import get_database
from app.services.business_notification_service import create_business_notification
from app.services.smart_order_service import is_stock_required

RESERVABLE_STATUSES = {"pending", "confirmed", "processing", "ready"}
DEDUCT_STATUSES = {"completed"}
RESTORE_STATUSES = {"cancelled", "rejected"}


def _line_quantity(line: dict[str, Any]) -> float:
    try:
        quantity = float(line.get("quantity", 1) or 1)
    except (TypeError, ValueError):
        quantity = 1.0
    return max(quantity, 1.0)


def _line_item_id(line: dict[str, Any]) -> ObjectId:
    raw_item_id = line.get("itemId")
    if isinstance(raw_item_id, ObjectId):
        return raw_item_id
    return parse_object_id(str(raw_item_id or ""), "itemId")


def _get_variant_index(item: dict[str, Any], line: dict[str, Any]) -> int | None:
    variants = item.get("variants") or []
    selected_index = line.get("selectedVariantIndex")
    if selected_index is not None and selected_index != "":
        try:
            index = int(selected_index)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid selected variant index.")
        if 0 <= index < len(variants) and variants[index].get("isActive", True):
            return index
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected variant is no longer available.")

    variant_sku = str(line.get("variantSku", "") or "").strip().lower()
    if variant_sku:
        for index, variant in enumerate(variants):
            if variant.get("isActive", True) and str(variant.get("sku", "") or "").strip().lower() == variant_sku:
                return index

    selected_name = str(line.get("selectedVariantName", "") or "").strip().lower()
    if selected_name:
        for index, variant in enumerate(variants):
            if variant.get("isActive", True) and str(variant.get("name", "") or "").strip().lower() == selected_name:
                return index

    return None


def _available_item_quantity(item: dict[str, Any]) -> float:
    stock = item.get("stock") or {}
    return max(0.0, float(stock.get("quantity", 0) or 0) - float(stock.get("reservedQuantity", 0) or 0))


def _available_variant_quantity(variant: dict[str, Any]) -> float:
    return max(0.0, float(variant.get("stockQuantity", 0) or 0) - float(variant.get("reservedQuantity", 0) or 0))


def _requires_stock(item: dict[str, Any], line: dict[str, Any]) -> bool:
    snapshot = line.get("stockSnapshot") or {}
    if snapshot.get("tracked") is False:
        return False
    return is_stock_required(item)


async def _create_movement(
    tenant_id: ObjectId,
    transaction: dict[str, Any],
    line: dict[str, Any],
    movement_type: str,
    quantity: float,
    item: dict[str, Any],
    variant_index: int | None,
    actor_user_id: ObjectId | None = None,
) -> dict[str, Any]:
    db = get_database()
    now = datetime.now(timezone.utc)
    variant = (item.get("variants") or [])[variant_index] if variant_index is not None and variant_index < len(item.get("variants", [])) else None
    movement = {
        "tenantId": tenant_id,
        "transactionId": transaction.get("_id"),
        "transactionNumber": transaction.get("transactionNumber", ""),
        "itemId": item.get("_id"),
        "itemName": item.get("name", line.get("name", "")),
        "variantIndex": variant_index,
        "variantName": (variant or {}).get("name", line.get("selectedVariantName", "")),
        "movementType": movement_type,
        "quantity": quantity,
        "source": "transaction",
        "actorUserId": actor_user_id,
        "createdAt": now,
    }
    movement["_id"] = (await db.inventory_movements.insert_one(movement)).inserted_id
    return movement


async def _notify_low_stock_if_needed(tenant_id: ObjectId, item: dict[str, Any]) -> None:
    try:
        stock = item.get("stock") or {}
        if item.get("isStockTracked", True) and not item.get("variants"):
            quantity = float(stock.get("quantity", 0) or 0)
            threshold = float(stock.get("lowStockThreshold", 0) or 0)
            if threshold > 0 and quantity <= threshold:
                await create_business_notification(
                    tenant_id,
                    "low_stock",
                    f"Low stock: {item.get('name', 'Item')}",
                    f"{item.get('name', 'Item')} stock is {quantity:g}, which is at or below the threshold {threshold:g}.",
                    priority="high",
                    metadata={"itemId": str(item.get("_id")), "itemName": item.get("name", ""), "quantity": quantity, "threshold": threshold},
                    source_key=f"low-stock-{tenant_id}-{item.get('_id')}",
                )
        for index, variant in enumerate(item.get("variants") or []):
            quantity = float(variant.get("stockQuantity", 0) or 0)
            threshold = float(variant.get("lowStockThreshold", 0) or 0)
            if threshold > 0 and quantity <= threshold:
                await create_business_notification(
                    tenant_id,
                    "low_stock",
                    f"Low stock: {item.get('name', 'Item')} / {variant.get('name', 'Variant')}",
                    f"{item.get('name', 'Item')} variant {variant.get('name', 'Variant')} stock is {quantity:g}, at or below threshold {threshold:g}.",
                    priority="high",
                    metadata={
                        "itemId": str(item.get("_id")),
                        "itemName": item.get("name", ""),
                        "variantIndex": index,
                        "variantName": variant.get("name", ""),
                        "quantity": quantity,
                        "threshold": threshold,
                    },
                    source_key=f"low-stock-{tenant_id}-{item.get('_id')}-{index}",
                )
    except Exception:
        # Stock notifications must never block order/payment workflows.
        return


async def reserve_transaction_stock(transaction: dict[str, Any], actor_user_id: ObjectId | None = None) -> dict[str, Any]:
    """Reserve stock for order lines. Services/non-stock items are skipped."""
    if transaction.get("transactionType") != "order":
        return transaction
    if transaction.get("inventoryStatus") in {"reserved", "deducted"}:
        return transaction

    db = get_database()
    tenant_id = transaction["tenantId"]
    now = datetime.now(timezone.utc)
    movements: list[dict[str, Any]] = []
    reservable_lines = []

    for line in transaction.get("items") or []:
        quantity = _line_quantity(line)
        item = await db.items.find_one({"_id": _line_item_id(line), "tenantId": tenant_id, "status": {"$ne": "archived"}})
        if not item or not _requires_stock(item, line):
            continue
        variant_index = _get_variant_index(item, line)
        if variant_index is not None:
            variant = item.get("variants", [])[variant_index]
            available = _available_variant_quantity(variant)
        else:
            available = _available_item_quantity(item)
        if available < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not enough stock for {item.get('name', line.get('name', 'item'))}. Available: {available:g}, requested: {quantity:g}.",
            )
        reservable_lines.append((line, item, variant_index, quantity))

    if not reservable_lines:
        await db.transactions.update_one(
            {"_id": transaction["_id"]},
            {"$set": {"inventoryStatus": "not_required", "inventoryUpdatedAt": now, "updatedAt": now}},
        )
        updated = await db.transactions.find_one({"_id": transaction["_id"]})
        return updated or transaction

    for line, item, variant_index, quantity in reservable_lines:
        if variant_index is not None:
            await db.items.update_one(
                {"_id": item["_id"], "tenantId": tenant_id},
                {"$inc": {f"variants.{variant_index}.reservedQuantity": quantity}, "$set": {"updatedAt": now}},
            )
        else:
            await db.items.update_one(
                {"_id": item["_id"], "tenantId": tenant_id},
                {"$inc": {"stock.reservedQuantity": quantity}, "$set": {"updatedAt": now}},
            )
        movement = await _create_movement(tenant_id, transaction, line, "reserve", quantity, item, variant_index, actor_user_id)
        movements.append(movement)

    await db.transactions.update_one(
        {"_id": transaction["_id"]},
        {
            "$set": {"inventoryStatus": "reserved", "inventoryUpdatedAt": now, "updatedAt": now},
            "$push": {"inventoryMovements": {"$each": movements}},
        },
    )
    updated = await db.transactions.find_one({"_id": transaction["_id"]})
    return updated or transaction


async def release_transaction_stock(transaction: dict[str, Any], actor_user_id: ObjectId | None = None) -> dict[str, Any]:
    return await restore_transaction_stock(transaction, actor_user_id)


async def restore_transaction_stock(transaction: dict[str, Any], actor_user_id: ObjectId | None = None) -> dict[str, Any]:
    if transaction.get("transactionType") != "order" or transaction.get("inventoryStatus") not in {"reserved", "deducted"}:
        return transaction

    db = get_database()
    tenant_id = transaction["tenantId"]
    now = datetime.now(timezone.utc)
    movements: list[dict[str, Any]] = []
    restore_from_deducted = transaction.get("inventoryStatus") == "deducted"

    for line in transaction.get("items") or []:
        quantity = _line_quantity(line)
        item = await db.items.find_one({"_id": _line_item_id(line), "tenantId": tenant_id, "status": {"$ne": "archived"}})
        if not item or not _requires_stock(item, line):
            continue
        variant_index = _get_variant_index(item, line)
        if variant_index is not None:
            variant = item.get("variants", [])[variant_index]
            reserved = float(variant.get("reservedQuantity", 0) or 0)
            stock_quantity = float(variant.get("stockQuantity", 0) or 0)
            update_doc = {
                "$set": {"updatedAt": now},
            }
            if restore_from_deducted:
                update_doc["$set"][f"variants.{variant_index}.stockQuantity"] = stock_quantity + quantity
            if reserved > 0:
                update_doc["$set"][f"variants.{variant_index}.reservedQuantity"] = max(0.0, reserved - quantity)
            await db.items.update_one({"_id": item["_id"], "tenantId": tenant_id}, update_doc)
        else:
            stock = item.get("stock") or {}
            reserved = float(stock.get("reservedQuantity", 0) or 0)
            stock_quantity = float(stock.get("quantity", 0) or 0)
            update_doc = {
                "$set": {"updatedAt": now},
            }
            if restore_from_deducted:
                update_doc["$set"]["stock.quantity"] = stock_quantity + quantity
            if reserved > 0:
                update_doc["$set"]["stock.reservedQuantity"] = max(0.0, reserved - quantity)
            await db.items.update_one({"_id": item["_id"], "tenantId": tenant_id}, update_doc)
        movement = await _create_movement(tenant_id, transaction, line, "release", quantity, item, variant_index, actor_user_id)
        movements.append(movement)

    await db.transactions.update_one(
        {"_id": transaction["_id"]},
        {
            "$set": {"inventoryStatus": "released", "inventoryUpdatedAt": now, "updatedAt": now},
            "$push": {"inventoryMovements": {"$each": movements}},
        },
    )
    updated = await db.transactions.find_one({"_id": transaction["_id"]})
    return updated or transaction


async def deduct_transaction_stock(transaction: dict[str, Any], actor_user_id: ObjectId | None = None) -> dict[str, Any]:
    if transaction.get("transactionType") != "order" or transaction.get("inventoryStatus") == "deducted":
        return transaction
    if transaction.get("inventoryStatus") not in {"reserved", "not_required"}:
        transaction = await reserve_transaction_stock(transaction, actor_user_id)

    if transaction.get("inventoryStatus") == "not_required":
        return transaction

    db = get_database()
    tenant_id = transaction["tenantId"]
    now = datetime.now(timezone.utc)
    movements: list[dict[str, Any]] = []
    touched_item_ids: set[ObjectId] = set()

    for line in transaction.get("items") or []:
        quantity = _line_quantity(line)
        item = await db.items.find_one({"_id": _line_item_id(line), "tenantId": tenant_id, "status": {"$ne": "archived"}})
        if not item or not _requires_stock(item, line):
            continue
        variant_index = _get_variant_index(item, line)
        if variant_index is not None:
            variant = item.get("variants", [])[variant_index]
            current_qty = float(variant.get("stockQuantity", 0) or 0)
            reserved = float(variant.get("reservedQuantity", 0) or 0)
            await db.items.update_one(
                {"_id": item["_id"], "tenantId": tenant_id},
                {
                    "$set": {
                        f"variants.{variant_index}.stockQuantity": max(0.0, current_qty - quantity),
                        f"variants.{variant_index}.reservedQuantity": max(0.0, reserved - quantity),
                        "updatedAt": now,
                    }
                },
            )
        else:
            stock = item.get("stock") or {}
            current_qty = float(stock.get("quantity", 0) or 0)
            reserved = float(stock.get("reservedQuantity", 0) or 0)
            await db.items.update_one(
                {"_id": item["_id"], "tenantId": tenant_id},
                {"$set": {"stock.quantity": max(0.0, current_qty - quantity), "stock.reservedQuantity": max(0.0, reserved - quantity), "updatedAt": now}},
            )
        touched_item_ids.add(item["_id"])
        movement = await _create_movement(tenant_id, transaction, line, "deduct", quantity, item, variant_index, actor_user_id)
        movements.append(movement)

    await db.transactions.update_one(
        {"_id": transaction["_id"]},
        {
            "$set": {"inventoryStatus": "deducted", "inventoryUpdatedAt": now, "updatedAt": now},
            "$push": {"inventoryMovements": {"$each": movements}},
        },
    )
    for item_id in touched_item_ids:
        latest_item = await db.items.find_one({"_id": item_id, "tenantId": tenant_id})
        if latest_item:
            await _notify_low_stock_if_needed(tenant_id, latest_item)
    updated = await db.transactions.find_one({"_id": transaction["_id"]})
    return updated or transaction


async def apply_transaction_inventory_transition(previous: dict[str, Any], updated: dict[str, Any], actor_user_id: ObjectId | None = None) -> dict[str, Any]:
    if updated.get("transactionType") != "order":
        return updated
    previous_status = previous.get("status")
    next_status = updated.get("status")
    if previous_status == next_status:
        return updated
    if next_status in RESTORE_STATUSES:
        return await restore_transaction_stock(updated, actor_user_id)
    if next_status in DEDUCT_STATUSES:
        return await deduct_transaction_stock(updated, actor_user_id)
    if next_status in RESERVABLE_STATUSES and updated.get("inventoryStatus") not in {"reserved", "deducted", "not_required"}:
        return await reserve_transaction_stock(updated, actor_user_id)
    return updated


async def get_inventory_movements_for_transaction(tenant_id: ObjectId, transaction_id: ObjectId) -> list[dict[str, Any]]:
    db = get_database()
    cursor = db.inventory_movements.find({"tenantId": tenant_id, "transactionId": transaction_id}).sort("createdAt", -1)
    return [serialize_document(row) async for row in cursor]
