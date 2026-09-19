"""Phase 40A: a chosen variant must survive the cart, and the cart must not leak.

Two live bugs are pinned here:

* the cart stored only ``{itemId, quantity}`` while the order builder read four variant
  fields back out of it, so "Blue / Large" quietly became whatever the default variant
  was at checkout;
* ``get_customer_cart`` was the one customer-facing path that serialized the raw item
  document instead of ``customer_item_view``, handing the customer the business's cost
  price and exact stock levels.
"""

import unittest

from bson import ObjectId

from app.core.item_views import customer_item_view
from app.services.customer_portal_service import (
    build_cart_line,
    cart_line_key,
    cart_line_unit_price,
    find_cart_line,
)


class AddRequest:
    """Stand-in for CartItemCreateRequest."""

    def __init__(self, quantity=1, selectedVariantIndex=None, selectedVariantName="",
                 selectedOptions=None, variantSku=""):
        self.quantity = quantity
        self.selectedVariantIndex = selectedVariantIndex
        self.selectedVariantName = selectedVariantName
        self.selectedOptions = selectedOptions or {}
        self.variantSku = variantSku


def shirt(**overrides):
    item = {
        "_id": ObjectId(),
        "name": "Cotton Shirt",
        "price": 2000,
        "costPrice": 900,
        "currency": "PKR",
        "isStockTracked": True,
        "stock": {"quantity": 40, "reservedQuantity": 3, "lowStockThreshold": 5},
        "variants": [
            {"name": "Blue / Large", "sku": "SH-BL-L", "price": 2200, "isActive": True,
             "stockQuantity": 10, "reservedQuantity": 1, "optionValues": {"Color": "Blue", "Size": "Large"}},
            {"name": "Red / Small", "sku": "SH-RD-S", "price": 1900, "isActive": True,
             "stockQuantity": 8, "reservedQuantity": 0, "optionValues": {"Color": "Red", "Size": "Small"}},
        ],
    }
    item.update(overrides)
    return item


class CartLineBuildingTests(unittest.TestCase):
    def test_a_chosen_variant_is_stored_on_the_line(self):
        item = shirt()
        line = build_cart_line(item, AddRequest(quantity=2, selectedVariantIndex=0))
        self.assertEqual(line["selectedVariantIndex"], 0)
        self.assertEqual(line["selectedVariantName"], "Blue / Large")
        self.assertEqual(line["variantSku"], "SH-BL-L")
        self.assertEqual(line["selectedOptions"], {"Color": "Blue", "Size": "Large"})

    def test_a_variant_can_be_chosen_by_sku(self):
        line = build_cart_line(shirt(), AddRequest(variantSku="SH-RD-S"))
        self.assertEqual(line["selectedVariantIndex"], 1)
        self.assertEqual(line["selectedVariantName"], "Red / Small")

    def test_a_variant_can_be_chosen_by_options(self):
        line = build_cart_line(shirt(), AddRequest(selectedOptions={"Color": "Red", "Size": "Small"}))
        self.assertEqual(line["selectedVariantIndex"], 1)

    def test_an_item_without_variants_stores_none(self):
        line = build_cart_line(shirt(variants=[]), AddRequest(quantity=1))
        self.assertIsNone(line["selectedVariantIndex"])
        self.assertEqual(line["selectedVariantName"], "")

    def test_every_line_gets_its_own_id(self):
        item = shirt()
        first = build_cart_line(item, AddRequest(selectedVariantIndex=0))
        second = build_cart_line(item, AddRequest(selectedVariantIndex=1))
        self.assertTrue(first["lineId"])
        self.assertNotEqual(first["lineId"], second["lineId"])

    def test_an_unavailable_variant_is_refused_at_add_time(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as context:
            build_cart_line(shirt(), AddRequest(selectedVariantIndex=9))
        self.assertEqual(context.exception.status_code, 422)


class CartLineIdentityTests(unittest.TestCase):
    """Merging on itemId alone is what lost one of two variants."""

    def test_two_variants_of_one_item_are_two_lines(self):
        item = shirt()
        blue = build_cart_line(item, AddRequest(selectedVariantIndex=0))
        red = build_cart_line(item, AddRequest(selectedVariantIndex=1))
        self.assertNotEqual(cart_line_key(blue), cart_line_key(red))

    def test_the_same_variant_added_twice_is_one_line(self):
        item = shirt()
        first = build_cart_line(item, AddRequest(selectedVariantIndex=0))
        second = build_cart_line(item, AddRequest(selectedVariantIndex=0))
        self.assertEqual(cart_line_key(first), cart_line_key(second))

    def test_a_variantless_item_added_twice_is_one_line(self):
        item = shirt(variants=[])
        first = build_cart_line(item, AddRequest())
        second = build_cart_line(item, AddRequest())
        self.assertEqual(cart_line_key(first), cart_line_key(second))


class CartLineLookupTests(unittest.TestCase):
    def test_a_line_is_found_by_its_id(self):
        item = shirt()
        blue = build_cart_line(item, AddRequest(selectedVariantIndex=0))
        red = build_cart_line(item, AddRequest(selectedVariantIndex=1))
        cart = {"items": [blue, red]}
        self.assertIs(find_cart_line(cart, red["lineId"]), red)

    def test_a_legacy_line_without_an_id_is_still_found_by_item(self):
        legacy = {"itemId": ObjectId(), "quantity": 2}
        cart = {"items": [legacy]}
        self.assertIs(find_cart_line(cart, str(legacy["itemId"])), legacy)

    def test_an_unknown_reference_finds_nothing(self):
        cart = {"items": [build_cart_line(shirt(), AddRequest())]}
        self.assertIsNone(find_cart_line(cart, "nope"))
        self.assertIsNone(find_cart_line(cart, ""))

    def test_removing_one_variant_leaves_the_other(self):
        item = shirt()
        blue = build_cart_line(item, AddRequest(selectedVariantIndex=0))
        red = build_cart_line(item, AddRequest(selectedVariantIndex=1))
        cart = {"items": [blue, red]}
        target = find_cart_line(cart, blue["lineId"])
        remaining = [line for line in cart["items"] if line is not target]
        self.assertEqual(remaining, [red])


class CartPricingTests(unittest.TestCase):
    def test_a_variant_line_is_priced_from_the_variant(self):
        item = shirt()
        line = build_cart_line(item, AddRequest(selectedVariantIndex=0))
        self.assertEqual(cart_line_unit_price(item, line), 2200)

    def test_a_base_line_is_priced_from_the_item(self):
        item = shirt()
        line = build_cart_line(item, AddRequest())
        self.assertEqual(cart_line_unit_price(item, line), 2000)

    def test_a_missing_item_prices_at_zero_rather_than_raising(self):
        self.assertEqual(cart_line_unit_price(None, {"selectedVariantIndex": 0}), 0.0)


class CartExposureTests(unittest.TestCase):
    """The cart is a customer-facing surface and must use the customer projection."""

    def test_the_customer_projection_hides_cost_and_exact_stock(self):
        view = customer_item_view(shirt())
        self.assertNotIn("costPrice", view)
        self.assertNotIn("quantity", view["stock"])
        self.assertNotIn("reservedQuantity", view["stock"])
        for variant in view["variants"]:
            self.assertNotIn("stockQuantity", variant)
            self.assertNotIn("reservedQuantity", variant)

    def test_the_cart_builds_its_lines_through_that_projection(self):
        import inspect

        from app.services import customer_portal_service

        source = inspect.getsource(customer_portal_service.get_customer_cart)
        self.assertIn("customer_item_view(source_item)", source)
        self.assertNotIn("serialize_document(item_map", source)


class CartRequestContractTests(unittest.TestCase):
    def test_the_add_request_accepts_the_variant_the_order_builder_reads(self):
        from app.schemas.customer_portal_schema import CartItemCreateRequest

        fields = set(CartItemCreateRequest.model_fields)
        # These four are read back out of the cart when the order is built.
        for field in ("selectedVariantIndex", "selectedVariantName", "selectedOptions", "variantSku"):
            self.assertIn(field, fields)

    def test_quantity_bounds_are_still_enforced(self):
        from pydantic import ValidationError

        from app.schemas.customer_portal_schema import CartItemCreateRequest

        with self.assertRaises(ValidationError):
            CartItemCreateRequest(tenantId="t", itemId="i", quantity=0)
        with self.assertRaises(ValidationError):
            CartItemCreateRequest(tenantId="t", itemId="i", quantity=100)


if __name__ == "__main__":
    unittest.main()


class StockReservationSurvivalTests(unittest.TestCase):
    """An item edit must not disturb live reservations.

    `reservedQuantity` is owned by the reservation workflow. When an ordinary edit reset
    it, available stock was overstated (so the item could be oversold) and the matching
    release or deduct then failed with "reservation needs reconciliation", leaving those
    orders unable to complete or cancel.
    """

    def test_reserved_quantity_is_not_a_client_input(self):
        from app.schemas.item_schema import StockRequest

        self.assertNotIn("reservedQuantity", StockRequest.model_fields)

    def test_an_edit_carries_the_stored_reservation(self):
        from app.services.item_service import _stock_dict

        incoming = type("Stock", (), {"quantity": 50.0, "lowStockThreshold": 5.0})()
        result = _stock_dict(incoming, {"quantity": 20.0, "reservedQuantity": 7.0})
        self.assertEqual(result["quantity"], 50.0, "the owner's new quantity is applied")
        self.assertEqual(result["reservedQuantity"], 7.0, "but the live reservation is untouched")

    def test_a_new_item_starts_with_nothing_reserved(self):
        from app.services.item_service import _stock_dict

        incoming = type("Stock", (), {"quantity": 10.0, "lowStockThreshold": 1.0})()
        self.assertEqual(_stock_dict(incoming)["reservedQuantity"], 0.0)

    def test_variant_reservations_follow_the_sku_not_the_position(self):
        """Matching by list position moved a reservation onto a different variant as soon
        as the owner reordered or removed one."""
        from app.services.item_service import _carry_variant_reservations

        stored = [
            {"sku": "SHIRT-S", "name": "Small", "reservedQuantity": 2.0},
            {"sku": "SHIRT-M", "name": "Medium", "reservedQuantity": 5.0},
        ]
        # The owner reorders them and renames one.
        incoming = [{"sku": "SHIRT-M", "name": "Medium (regular)"}, {"sku": "SHIRT-S", "name": "Small"}]
        carried = _carry_variant_reservations(incoming, stored)
        self.assertEqual(carried[0]["reservedQuantity"], 5.0)
        self.assertEqual(carried[1]["reservedQuantity"], 2.0)

    def test_a_brand_new_variant_reserves_nothing(self):
        from app.services.item_service import _carry_variant_reservations

        carried = _carry_variant_reservations([{"sku": "SHIRT-L", "name": "Large"}], [])
        self.assertEqual(carried[0]["reservedQuantity"], 0.0)


class VariantReservationEditShapesTests(unittest.TestCase):
    """Every shape of variant edit an owner can make, and what must happen to the live
    reservations attached to those variants."""

    STORED = [
        {"sku": "S", "name": "Small", "reservedQuantity": 2.0},
        {"sku": "M", "name": "Medium", "reservedQuantity": 5.0},
    ]

    def _carry(self, incoming):
        from app.services.item_service import _carry_variant_reservations

        return [(v.get("sku"), v["reservedQuantity"]) for v in _carry_variant_reservations(incoming, self.STORED)]

    def test_reordering_and_renaming_follows_the_sku(self):
        result = self._carry([{"sku": "M", "name": "Medium regular"}, {"sku": "S", "name": "Small"}])
        self.assertEqual(result, [("M", 5.0), ("S", 2.0)])

    def test_correcting_a_sku_typo_keeps_the_reservation(self):
        """The SKU is the identity key, so editing it used to silently drop the hold to
        zero - the exact failure this function exists to prevent."""
        result = self._carry([{"sku": "SML", "name": "Small"}, {"sku": "M", "name": "Medium"}])
        self.assertEqual(result, [("SML", 2.0), ("M", 5.0)])

    def test_replacing_the_list_does_not_inherit_a_stranger_reservation(self):
        """Position only means something when the list was edited in place. A shorter
        list is a replacement, and guessing would move a customer's hold onto a
        different product."""
        self.assertEqual(self._carry([{"sku": "L", "name": "Large"}]), [("L", 0.0)])

    def test_adding_a_variant_leaves_the_others_alone(self):
        result = self._carry(
            [{"sku": "S", "name": "Small"}, {"sku": "M", "name": "Medium"}, {"sku": "L", "name": "Large"}]
        )
        self.assertEqual(result, [("S", 2.0), ("M", 5.0), ("L", 0.0)])

    def test_an_untouched_list_is_unchanged(self):
        result = self._carry([{"sku": "S", "name": "Small"}, {"sku": "M", "name": "Medium"}])
        self.assertEqual(result, [("S", 2.0), ("M", 5.0)])
