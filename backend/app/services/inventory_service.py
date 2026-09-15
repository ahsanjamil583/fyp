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


async def _adjust_stock(db, tenant_id, item_id, variant_index, quantity, operation):
    """Compare-and-swap stock so concurrent orders cannot overwrite each other."""
    for _ in range(8):
        item = await db.items.find_one({"_id": item_id, "tenantId": tenant_id})
        if not item:
            raise HTTPException(status_code=409, detail="An ordered item no longer exists.")
        if variant_index is None:
            stock = item.get("stock") or {}
            quantity_key, reserved_key = "stock.quantity", "stock.reservedQuantity"
            quantity_field = "quantity"
        else:
            variants = item.get("variants") or []
            if variant_index >= len(variants):
                raise HTTPException(status_code=409, detail="An ordered variant no longer exists.")
            stock = variants[variant_index]
            quantity_key = f"variants.{variant_index}.stockQuantity"
            reserved_key = f"variants.{variant_index}.reservedQuantity"
            quantity_field = "stockQuantity"
        available = float(stock.get(quantity_field, 0) or 0)
        reserved = float(stock.get("reservedQuantity", 0) or 0)
        if operation == "reserve" and (
            item.get("status") == "archived" or available - reserved < quantity
        ):
            raise HTTPException(status_code=409, detail=f"Not enough stock for {item.get('name', 'item')}.")
        if operation in {"release", "deduct"} and reserved < quantity:
            raise HTTPException(status_code=409, detail="Inventory reservation needs reconciliation.")
        if operation == "deduct" and available < quantity:
            raise HTTPException(status_code=409, detail="Inventory quantity needs reconciliation.")
        increments = {
            "reserve": {reserved_key: quantity},
            "release": {reserved_key: -quantity},
            "deduct": {reserved_key: -quantity, quantity_key: -quantity},
            "return": {quantity_key: quantity},
        }[operation]
        query = {
            "_id": item_id, "tenantId": tenant_id,
            quantity_key: stock[quantity_field] if quantity_field in stock else {"$exists": False},
            reserved_key: stock["reservedQuantity"] if "reservedQuantity" in stock else {"$exists": False},
        }
        if operation == "reserve":
            query["status"] = {"$ne": "archived"}
        result = await db.items.update_one(query, {
            "$inc": increments, "$set": {"updatedAt": datetime.now(timezone.utc)},
        })
        if result.matched_count:
            return increments
    raise HTTPException(status_code=409, detail="Stock changed during this request. Please retry.")


async def _change_transaction_stock(transaction, operation, actor_user_id=None):
    if transaction.get("transactionType") != "order":
        return transaction
    db = get_database()
    query = {"_id": transaction["_id"], "tenantId": transaction["tenantId"]}
    current = await db.transactions.find_one(query)
    if not current:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    previous_status = current.get("inventoryStatus")
    if current.get("inventoryOperation"):
        raise HTTPException(status_code=409, detail="Inventory update in progress or awaiting reconciliation.")
    if operation == "reserve" and previous_status in {"reserved", "deducted", "not_required"}:
        return current
    if operation == "restore" and previous_status not in {"reserved", "deducted"}:
        return current
    if operation == "deduct" and previous_status in {"deducted", "not_required"}:
        return current
    if operation == "deduct" and previous_status != "reserved":
        current = await _change_transaction_stock(current, "reserve", actor_user_id)
        if current.get("inventoryStatus") == "not_required":
            return current
        previous_status = current.get("inventoryStatus")

    # A persisted claim also prevents two workers from processing the same order.
    # A process crash deliberately leaves the claim for reconciliation, not replay.
    claim = await db.transactions.update_one(
        {**query, "inventoryStatus": previous_status, "inventoryOperation": {"$exists": False}},
        {"$set": {"inventoryOperation": operation, "inventoryUpdatedAt": datetime.now(timezone.utc)}},
    )
    if not claim.matched_count:
        raise HTTPException(status_code=409, detail="This order is being updated. Please reload.")
    applied = []
    movement_ids = []
    try:
        lines = {}
        for line in current.get("items") or []:
            if not line.get("itemId"):
                # A manually typed counter line, or a line from an imported historical
                # sheet. There is no catalog row behind it, so there is no stock to move.
                continue
            item_id = _line_item_id(line)
            item = await db.items.find_one({"_id": item_id, "tenantId": current["tenantId"]})
            if not item:
                raise HTTPException(status_code=409, detail="An ordered item no longer exists.")
            if not _requires_stock(item, line):
                continue
            variant_index = _get_variant_index(item, line)
            key = (item_id, variant_index)
            if key not in lines:
                lines[key] = [line, item, 0.0]
            lines[key][2] += _line_quantity(line)

        stock_operation = (
            "return" if previous_status == "deducted" else "release"
        ) if operation == "restore" else operation
        movements = []
        for (item_id, variant_index), (line, item, quantity) in lines.items():
            increments = await _adjust_stock(
                db, current["tenantId"], item_id, variant_index, quantity, stock_operation,
            )
            applied.append((item_id, increments))
            movement = await _create_movement(
                current["tenantId"], current, line,
                "release" if operation == "restore" else operation,
                quantity, item, variant_index, actor_user_id,
            )
            movement_ids.append(movement["_id"])
            movements.append(movement)
        next_status = (
            "not_required" if not lines else
            {"reserve": "reserved", "restore": "released", "deduct": "deducted"}[operation]
        )
        now = datetime.now(timezone.utc)
        await db.transactions.update_one(query, {
            "$set": {"inventoryStatus": next_status, "inventoryUpdatedAt": now, "updatedAt": now},
            "$unset": {"inventoryOperation": ""},
            "$push": {"inventoryMovements": {"$each": movements}},
        })
    except Exception:
        # Undo only this request's deltas; never restore stale absolute quantities.
        try:
            for item_id, increments in reversed(applied):
                result = await db.items.update_one(
                    {"_id": item_id, "tenantId": current["tenantId"]},
                    {"$inc": {key: -value for key, value in increments.items()}},
                )
                if not result.matched_count:
                    raise RuntimeError("Inventory rollback item missing")
            if movement_ids:
                await db.inventory_movements.delete_many({"_id": {"$in": movement_ids}})
            await db.transactions.update_one(query, {"$unset": {"inventoryOperation": ""}})
        except Exception:
            await db.transactions.update_one(query, {"$set": {"inventoryOperation": "reconciliation_required"}})
        raise
    if operation == "deduct":
        for item_id, _ in applied:
            item = await db.items.find_one({"_id": item_id, "tenantId": current["tenantId"]})
            if item:
                await _notify_low_stock_if_needed(current["tenantId"], item)
    return await db.transactions.find_one(query) or current


async def reserve_transaction_stock(transaction, actor_user_id=None):
    return await _change_transaction_stock(transaction, "reserve", actor_user_id)


async def release_transaction_stock(transaction, actor_user_id=None):
    return await restore_transaction_stock(transaction, actor_user_id)


async def restore_transaction_stock(transaction, actor_user_id=None):
    return await _change_transaction_stock(transaction, "restore", actor_user_id)


async def deduct_transaction_stock(transaction, actor_user_id=None):
    return await _change_transaction_stock(transaction, "deduct", actor_user_id)


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
