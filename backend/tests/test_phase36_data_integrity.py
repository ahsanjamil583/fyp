"""Regression cover for the Phase 3 data-integrity work.

Duplicate catalog rows reached customers and inflated the owner agent's counts;
order requests silently discarded fields a client thought it was sending.
"""

import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from app.schemas.customer_portal_schema import CustomerDraftConfirmRequest, CustomerOrderCreateRequest
from app.schemas.public_website_schema import PublicOrderRequest


class StrictOrderSchemaTests(unittest.TestCase):
    """An ignored field means the caller and the server disagree about the order."""

    def test_unknown_field_is_rejected_not_dropped(self):
        with self.assertRaises(ValidationError) as ctx:
            CustomerOrderCreateRequest(tenantId="t", items=[{"itemId": "i", "quantity": 2}])
        self.assertEqual(ctx.exception.errors()[0]["type"], "extra_forbidden")

    def test_the_payload_the_cart_page_sends_is_still_valid(self):
        request = CustomerOrderCreateRequest(
            tenantId="t", transactionType="auto", paymentMethod="cod",
            fulfillment={"type": "delivery", "address": {"line1": "A", "city": "Lahore"}},
            notes="", customFields={},
        )
        self.assertEqual(request.paymentMethod, "cod")

    def test_the_payload_the_chat_page_sends_is_still_valid(self):
        request = CustomerDraftConfirmRequest(
            conversationId="opaque-token", transactionType="auto", paymentMethod="cod",
            items=[{"itemId": "i", "quantity": 1, "selectedVariantIndex": None,
                    "selectedVariantName": "", "selectedOptions": {}, "variantSku": ""}],
            fulfillment={"type": "pickup", "address": {}}, notes="", customFields={},
        )
        self.assertEqual(len(request.items), 1)

    def test_the_payload_the_public_page_sends_is_still_valid(self):
        request = PublicOrderRequest(
            customerName="QA Tester", customerPhone="03001234567", customerEmail="",
            conversationId="opaque-token", transactionType="auto", paymentMethod="cod",
            items=[{"itemId": "i", "quantity": 1, "selectedVariantIndex": None,
                    "selectedVariantName": "", "selectedOptions": {}, "variantSku": ""}],
            fulfillment={"type": "pickup", "address": {}}, notes="", customFields={},
        )
        self.assertEqual(request.customerName, "QA Tester")

    def test_public_order_rejects_unknown_field(self):
        with self.assertRaises(ValidationError):
            PublicOrderRequest(customerName="QA Tester", customerPhone="03001234567", totalAmount=999)


class DuplicateItemTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_insert_becomes_a_409_with_guidance(self):
        from app.services import item_service

        payload = type(
            "Payload",
            (),
            {
                "name": "Brown Leather Loafers", "sku": "", "price": 6200.0, "costPrice": 0.0,
                "itemType": "product", "description": "", "currency": "PKR", "unit": "piece",
                "images": [], "status": "active", "isSellable": True, "isBookable": False,
                "isStockTracked": True, "stock": None, "tags": [],
            },
        )()
        db = AsyncMock()
        db.items.insert_one = AsyncMock(side_effect=DuplicateKeyError("dup"))
        validated = {"categoryId": None, "serviceDetails": {}, "variants": [], "bundleComponents": [], "customFields": {}}

        with patch.object(item_service, "get_database", return_value=db), \
             patch.object(item_service, "_ensure_item_access", AsyncMock(return_value=ObjectId())), \
             patch.object(item_service, "ensure_tenant_module_usage_available", AsyncMock()), \
             patch.object(item_service, "_validate_item_payload", AsyncMock(return_value=validated)), \
             patch.object(item_service, "_stock_dict", return_value={}), \
             patch.object(item_service, "_image_dicts", return_value=[]), \
             patch.object(item_service, "_normalize_tags", return_value=[]):
            with self.assertRaises(HTTPException) as ctx:
                await item_service.create_item("t", payload, {"_id": ObjectId()})
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("already exists", ctx.exception.detail)

    def test_sku_collision_message_names_the_sku(self):
        from app.services.item_service import _duplicate_item_detail

        payload = type("Payload", (), {"name": "Loafers", "sku": "LOAF-42", "price": 1.0})()
        self.assertIn("LOAF-42", _duplicate_item_detail(payload))

    def test_nameless_collision_message_explains_the_options(self):
        from app.services.item_service import _duplicate_item_detail

        payload = type("Payload", (), {"name": "Loafers", "sku": "", "price": 1.0})()
        detail = _duplicate_item_detail(payload)
        self.assertIn("Loafers", detail)
        self.assertIn("archive", detail)


class DedupeGroupingTests(unittest.TestCase):
    """The migration must treat only genuinely indistinguishable rows as duplicates."""

    def setUp(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "scripts" / "dedupe_catalog_items.py"
        spec = importlib.util.spec_from_file_location("dedupe_catalog_items", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def _key(self, **overrides):
        base = {"tenantId": "t", "branchId": None, "name": "Blue Shirt", "price": 1000.0, "sku": ""}
        base.update(overrides)
        return self.module._group_key(base)

    def test_identical_rows_group_together(self):
        self.assertEqual(self._key(), self._key())

    def test_case_and_padding_do_not_create_a_false_distinction(self):
        self.assertEqual(self._key(), self._key(name="  blue shirt  "))

    def test_a_different_price_is_a_different_item(self):
        self.assertNotEqual(self._key(), self._key(price=1200.0))

    def test_a_different_branch_is_a_different_item(self):
        self.assertNotEqual(self._key(), self._key(branchId="branch-2"))

    def test_a_different_sku_is_a_different_item(self):
        self.assertNotEqual(self._key(), self._key(sku="SHIRT-1"))

    def test_a_different_tenant_never_collides(self):
        self.assertNotEqual(self._key(), self._key(tenantId="other"))


class ArchivedItemFilterTests(unittest.IsolatedAsyncioTestCase):
    async def _query_for(self, status_filter):
        from app.services import item_service

        captured = {}

        class Cursor:
            def sort(self, *a, **k): return self
            def skip(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def __aiter__(self): return self
            async def __anext__(self): raise StopAsyncIteration

        def find(query, *a, **k):
            captured["query"] = query
            return Cursor()

        db = AsyncMock()
        db.items.find = find
        db.items.count_documents = AsyncMock(return_value=0)
        with patch.object(item_service, "get_database", return_value=db), \
             patch.object(item_service, "_ensure_item_access", AsyncMock(return_value=ObjectId())):
            await item_service.list_items("t", {"_id": ObjectId()}, status_filter=status_filter)
        return captured["query"]

    async def test_default_view_hides_archived_items(self):
        self.assertEqual((await self._query_for(None))["status"], {"$ne": "archived"})

    async def test_archived_can_be_requested_explicitly(self):
        self.assertEqual((await self._query_for("archived"))["status"], "archived")

    async def test_all_returns_every_status(self):
        self.assertNotIn("status", await self._query_for("all"))


if __name__ == "__main__":
    unittest.main()
