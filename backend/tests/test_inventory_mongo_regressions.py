"""Opt-in real Mongo checks, confined to a new disposable audit database."""
import asyncio
import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.services.inventory_service import reserve_transaction_stock, deduct_transaction_stock, restore_transaction_stock


@unittest.skipUnless(os.environ.get("RUN_MONGO_TESTS") == "1", "Set RUN_MONGO_TESTS=1 for isolated Mongo regression tests")
class InventoryMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
        self.name = "bizxus_audit_test_" + uuid4().hex
        self.db = self.client[self.name]
        self.tenant = ObjectId()
        self.patcher = patch("app.services.inventory_service.get_database", return_value=self.db)
        self.patcher.start()

    async def asyncTearDown(self):
        self.patcher.stop()
        assert self.name.startswith("bizxus_audit_test_") and self.name != settings.mongodb_db_name
        await self.client.drop_database(self.name)
        self.client.close()

    async def item(self, stock=5, reserved=0, variants=None):
        item = {"_id": ObjectId(), "tenantId": self.tenant, "name": "Test item", "status": "active", "isStockTracked": True, "itemType": "product", "stock": {"quantity": stock, "reservedQuantity": reserved}, "variants": variants or []}
        await self.db.items.insert_one(item)
        return item

    async def order(self, lines, inventory_status="not_reserved"):
        order = {"_id": ObjectId(), "tenantId": self.tenant, "transactionType": "order", "inventoryStatus": inventory_status, "items": lines}
        await self.db.transactions.insert_one(order)
        return order

    async def test_concurrent_orders_cannot_oversell(self):
        item = await self.item()
        orders = [await self.order([{"itemId": item["_id"], "quantity": 4}]) for _ in range(2)]
        results = await asyncio.gather(*(reserve_transaction_stock(o) for o in orders), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, HTTPException) for r in results), 1)
        self.assertEqual((await self.db.items.find_one({"_id": item["_id"]}))["stock"]["reservedQuantity"], 4)

    async def test_duplicate_lines_are_combined_before_reserving(self):
        item = await self.item()
        order = await self.order([{"itemId": item["_id"], "quantity": 3}] * 2)
        with self.assertRaises(HTTPException):
            await reserve_transaction_stock(order)
        self.assertEqual((await self.db.items.find_one({"_id": item["_id"]}))["stock"]["reservedQuantity"], 0)

    async def test_partial_reservation_rolls_back(self):
        one, two = await self.item(), await self.item(stock=0)
        order = await self.order([{"itemId": i["_id"], "quantity": 2} for i in (one, two)])
        with self.assertRaises(HTTPException):
            await reserve_transaction_stock(order)
        self.assertEqual((await self.db.items.find_one({"_id": one["_id"]}))["stock"]["reservedQuantity"], 0)
        self.assertEqual(await self.db.inventory_movements.count_documents({}), 0)
        self.assertNotIn("inventoryOperation", await self.db.transactions.find_one({"_id": order["_id"]}))

    async def test_repeated_and_concurrent_order_reservation_is_idempotent(self):
        item = await self.item(stock=10)
        order = await self.order([{"itemId": item["_id"], "quantity": 2}])
        await asyncio.gather(reserve_transaction_stock(order), reserve_transaction_stock(order), return_exceptions=True)
        await reserve_transaction_stock(order)
        self.assertEqual((await self.db.items.find_one({"_id": item["_id"]}))["stock"]["reservedQuantity"], 2)

    async def test_completed_refund_preserves_other_orders_reservations(self):
        item = await self.item(stock=10, reserved=3)
        order = await self.order([{"itemId": item["_id"], "quantity": 2}])
        await reserve_transaction_stock(order)
        await deduct_transaction_stock(order)
        await deduct_transaction_stock(order)
        await restore_transaction_stock(order)
        await restore_transaction_stock(order)
        stock = (await self.db.items.find_one({"_id": item["_id"]}))["stock"]
        self.assertEqual(stock, {"quantity": 10, "reservedQuantity": 3})

    async def test_variant_refund_preserves_other_orders_reservations(self):
        item = await self.item(variants=[{"name": "Large", "isActive": True, "stockQuantity": 8, "reservedQuantity": 3}])
        order = await self.order([{"itemId": item["_id"], "quantity": 2, "selectedVariantIndex": 0}], "deducted")
        await restore_transaction_stock(order)
        variant = (await self.db.items.find_one({"_id": item["_id"]}))["variants"][0]
        self.assertEqual(variant["stockQuantity"], 10)
        self.assertEqual(variant["reservedQuantity"], 3)

    async def test_daily_revenue_excludes_other_days_and_rejected_orders(self):
        from app.services.reporting_service import generate_daily_summary
        for created, amount, status in ((datetime(2026, 9, 10, 18, tzinfo=timezone.utc), 1000, "completed"), (datetime(2026, 9, 10, 20, tzinfo=timezone.utc), 200, "completed"), (datetime(2026, 9, 11, 10, tzinfo=timezone.utc), 500, "rejected")):
            await self.db.transactions.insert_one({"tenantId": self.tenant, "transactionType": "order", "createdAt": created, "status": status, "pricing": {"total": amount}, "items": [{"itemId": ObjectId(), "name": "Test", "quantity": 1, "subtotal": amount}]})
        with patch("app.services.reporting_service.get_database", return_value=self.db), patch("app.services.reporting_service._get_reporting_access", AsyncMock(return_value=(str(self.tenant), {"_id": self.tenant, "name": "Test"}))), patch("app.services.reporting_service.get_analytics_summary", AsyncMock(return_value={"revenue": {"grossRevenue": 99999}})), patch("app.services.reporting_service.sync_low_stock_notifications", AsyncMock()), patch("app.services.reporting_service.create_business_notification", AsyncMock()):
            report = await generate_daily_summary(str(self.tenant), {}, "2026-09-11")
        self.assertEqual(report["metrics"]["grossRevenue"], 200)
        self.assertEqual(report["metrics"]["newOrders"], 2)
        self.assertEqual(report["topItems"][0]["revenue"], 200)

    async def test_scheduled_report_is_claimed_once_across_workers(self):
        from app.services.report_delivery_service import run_scheduled_report_delivery
        from app.schemas.report_delivery_schema import ScheduledReportRunRequest
        await self.db.report_delivery_settings.insert_one({"tenantId": self.tenant, "enabled": True, "whatsappEnabled": True, "timezone": "Asia/Karachi"})
        with patch("app.services.report_delivery_service.get_database", return_value=self.db), patch("app.services.report_delivery_service._get_delivery_access", AsyncMock(return_value=(self.tenant, {}))), patch("app.services.report_delivery_service.deliver_daily_summary", AsyncMock(return_value={"deliveryStatus": "queued"})) as sender:
            payload = ScheduledReportRunRequest(summaryDate="2026-09-11", dryRun=False)
            results = await asyncio.gather(*(run_scheduled_report_delivery(str(self.tenant), payload, {}) for _ in range(2)))
        sender.assert_awaited_once()
        self.assertEqual({row["deliveryStatus"] for row in results}, {"queued", "already_processed"})

    async def test_outbound_claim_is_atomic_and_ack_updates_report(self):
        from app.services.whatsapp_outbound_service import claim_outbound_message, acknowledge_outbound_message
        message_id = ObjectId()
        await self.db.whatsapp_message_logs.insert_one({"_id": message_id, "tenantId": self.tenant, "provider": "baileys", "direction": "outbound", "deliveryStatus": "queued", "toPhone": "+923001234567", "messageText": "Test", "createdAt": datetime.now(timezone.utc)})
        await self.db.report_delivery_logs.insert_one({"tenantId": self.tenant, "providerLogId": str(message_id), "deliveryStatus": "queued"})
        with patch("app.services.whatsapp_outbound_service._authorize", AsyncMock(return_value=(self.db, self.tenant))):
            results = await asyncio.gather(*(claim_outbound_message(str(self.tenant), "test") for _ in range(2)))
            self.assertEqual(sum(row is not None for row in results), 1)
            await acknowledge_outbound_message(str(self.tenant), str(message_id), "test", "sent")
            with self.assertRaises(HTTPException):
                await acknowledge_outbound_message(str(self.tenant), str(message_id), "test", "sent")
        self.assertEqual((await self.db.report_delivery_logs.find_one({}))["deliveryStatus"], "sent")
