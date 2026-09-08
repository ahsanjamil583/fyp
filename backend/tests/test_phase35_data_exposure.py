"""Regression cover for the Phase 2 data-leakage work.

Catalog documents carry margin and exact inventory. Both were reaching anonymous
visitors through the public website, the customer portal, and AI draft orders.
"""

import unittest

from app.ai.agents.tools import format_catalog_for_prompt
from app.core.item_views import (
    LOW_STOCK_BAND,
    OWNER_ONLY_ITEM_FIELDS,
    STOCK_IN,
    STOCK_LOW,
    STOCK_OUT,
    STOCK_UNTRACKED,
    coarse_stock_status,
    customer_item_view,
    customer_stock_snapshot,
)


def _item(**overrides):
    base = {
        "_id": "abc",
        "name": "Brown Leather Loafers",
        "price": 6200.0,
        "costPrice": 3100.0,
        "currency": "PKR",
        "isStockTracked": True,
        "stock": {"quantity": 12.0, "reservedQuantity": 0.0, "lowStockThreshold": 2.0},
        "variants": [],
    }
    base.update(overrides)
    return base


class CostPriceTests(unittest.TestCase):
    def test_cost_price_is_removed_for_customers(self):
        view = customer_item_view(_item())
        self.assertNotIn("costPrice", view)
        self.assertEqual(view["price"], 6200.0, "the selling price must survive")

    def test_every_owner_only_field_is_removed(self):
        view = customer_item_view(_item())
        for field in OWNER_ONLY_ITEM_FIELDS:
            with self.subTest(field=field):
                self.assertNotIn(field, view)

    def test_variant_cost_price_is_removed(self):
        view = customer_item_view(_item(variants=[{"name": "42", "price": 6200.0, "costPrice": 3000.0}]))
        self.assertNotIn("costPrice", view["variants"][0])


class StockCoarseningTests(unittest.TestCase):
    def test_exact_quantities_never_reach_a_customer(self):
        view = customer_item_view(_item())
        self.assertNotIn("quantity", view["stock"])
        self.assertNotIn("reservedQuantity", view["stock"])
        self.assertNotIn("lowStockThreshold", view["stock"])

    def test_bands_reflect_availability(self):
        self.assertEqual(customer_item_view(_item())["stock"]["status"], STOCK_IN)
        self.assertEqual(
            customer_item_view(_item(stock={"quantity": 2.0, "reservedQuantity": 0.0}))["stock"]["status"], STOCK_LOW
        )
        self.assertEqual(
            customer_item_view(_item(stock={"quantity": 0.0, "reservedQuantity": 0.0}))["stock"]["status"], STOCK_OUT
        )

    def test_reserved_units_count_against_availability(self):
        view = customer_item_view(_item(stock={"quantity": 10.0, "reservedQuantity": 10.0}))
        self.assertEqual(view["stock"]["status"], STOCK_OUT)

    def test_untracked_items_report_untracked(self):
        view = customer_item_view(_item(isStockTracked=False))
        self.assertEqual(view["stock"]["status"], STOCK_UNTRACKED)
        self.assertTrue(view["stock"]["inStock"])

    def test_band_boundary(self):
        self.assertEqual(coarse_stock_status(LOW_STOCK_BAND), STOCK_LOW)
        self.assertEqual(coarse_stock_status(LOW_STOCK_BAND + 1), STOCK_IN)
        self.assertEqual(coarse_stock_status(0), STOCK_OUT)

    def test_variant_quantities_are_coarsened_too(self):
        view = customer_item_view(_item(variants=[{"name": "42", "stockQuantity": 3.0, "reservedQuantity": 0.0}]))
        variant = view["variants"][0]
        self.assertNotIn("stockQuantity", variant)
        self.assertNotIn("reservedQuantity", variant)
        self.assertEqual(variant["stockStatus"], STOCK_LOW)


class DraftOrderSnapshotTests(unittest.TestCase):
    """Draft lines are echoed back into the chat transcript."""

    def test_snapshot_loses_quantities_but_keeps_the_verdict(self):
        snapshot = customer_stock_snapshot(
            {"tracked": True, "available": True, "availableQuantity": 14.0, "reservedQuantity": 2.0, "requestedQuantity": 2}
        )
        self.assertNotIn("availableQuantity", snapshot)
        self.assertNotIn("reservedQuantity", snapshot)
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["status"], STOCK_IN)

    def test_out_of_stock_snapshot_is_still_actionable(self):
        snapshot = customer_stock_snapshot({"tracked": True, "available": False, "availableQuantity": 0.0})
        self.assertEqual(snapshot["status"], STOCK_OUT)
        self.assertFalse(snapshot["available"])

    def test_empty_snapshot_is_safe(self):
        self.assertEqual(customer_stock_snapshot(None), {})


class CatalogPromptTests(unittest.TestCase):
    """Anything in the prompt can be repeated back to whoever is chatting."""

    def test_customer_prompt_has_no_numbers(self):
        text = format_catalog_for_prompt([_item()], owner_channel=False)
        self.assertIn("in stock", text)
        self.assertNotIn("stock 12", text)

    def test_owner_prompt_keeps_exact_counts(self):
        text = format_catalog_for_prompt([_item()], owner_channel=True)
        self.assertIn("stock 12", text)

    def test_price_is_shown_to_both(self):
        for owner in (True, False):
            with self.subTest(owner=owner):
                self.assertIn("6,200", format_catalog_for_prompt([_item()], owner_channel=owner))


class RetentionTests(unittest.TestCase):
    def test_whatsapp_logs_have_a_bounded_retention_window(self):
        from app.core.config import settings

        self.assertGreater(settings.whatsapp_log_retention_days, 0)


if __name__ == "__main__":
    unittest.main()
