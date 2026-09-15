"""Phase 38: cashier module and historical order sheet import.

These cover the parts that are easy to get wrong and expensive to get wrong: the tenant
boundary a cashier must never cross, the pricing arithmetic printed on a receipt, what a
receipt is allowed to expose, and the sheet parser's tolerance for the shapes a real
business's spreadsheet actually has.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.services.cashier_order_service import (
    CASHIER_PAYMENT_METHODS,
    _build_fulfillment,
    _compute_pricing,
    _normalize_payment_method,
    _normalize_service_type,
    _order_scope_query,
    cashier_order_view,
)
from app.services.cashier_service import DEFAULT_CASHIER_PERMISSIONS, normalize_cashier_permissions
from app.services.order_import_service import (
    _fingerprint,
    _parse_rows,
    import_column_guide,
    map_order_status,
    map_payment_status,
    normalize_import_header,
    parse_import_date,
)


class _Pricing:
    def __init__(self, **kwargs):
        self.discountType = kwargs.get("discountType", "amount")
        self.discountValue = kwargs.get("discountValue", 0)
        self.taxType = kwargs.get("taxType", "amount")
        self.taxValue = kwargs.get("taxValue", 0)
        self.serviceCharge = kwargs.get("serviceCharge", 0)
        self.deliveryFee = kwargs.get("deliveryFee", 0)


ALL_ALLOWED = {"canViewAllCashierOrders": True, "canAddCustomItems": True, "canApplyDiscount": True}


class CashierPermissionTests(unittest.TestCase):
    def test_unknown_keys_are_dropped_and_defaults_applied(self):
        result = normalize_cashier_permissions({"canApplyDiscount": False, "canDeleteEverything": True})
        self.assertEqual(set(result), set(DEFAULT_CASHIER_PERMISSIONS))
        self.assertFalse(result["canApplyDiscount"])
        self.assertTrue(result["canAddCustomItems"])

    def test_missing_permissions_default_to_the_safe_value(self):
        self.assertFalse(normalize_cashier_permissions(None)["canViewAllCashierOrders"])


class CashierOrderScopeTests(unittest.TestCase):
    def test_scope_is_always_pinned_to_the_cashier_tenant(self):
        tenant_id = ObjectId()
        cashier = {"_id": ObjectId(), "permissions": ALL_ALLOWED}
        query = _order_scope_query(cashier, tenant_id)
        self.assertEqual(query["tenantId"], tenant_id)
        self.assertEqual(query["source"], "cashier")

    def test_a_cashier_without_the_grant_sees_only_their_own_orders(self):
        cashier_id = ObjectId()
        query = _order_scope_query({"_id": cashier_id, "permissions": {}}, ObjectId())
        self.assertEqual(query["cashier.cashierId"], cashier_id)

    def test_the_owner_grant_widens_the_scope_to_the_whole_business(self):
        query = _order_scope_query({"_id": ObjectId(), "permissions": ALL_ALLOWED}, ObjectId())
        self.assertNotIn("cashier.cashierId", query)


class CashierPricingTests(unittest.TestCase):
    def test_percent_discount_and_percent_tax_compound_in_the_right_order(self):
        pricing = _compute_pricing(1000, _Pricing(discountType="percent", discountValue=10, taxType="percent", taxValue=17), ALL_ALLOWED)
        self.assertEqual(pricing["discount"], 100)
        # Tax applies to the discounted base, not to the gross subtotal.
        self.assertEqual(pricing["tax"], 153)
        self.assertEqual(pricing["total"], 1053)

    def test_flat_charges_are_added_after_tax(self):
        pricing = _compute_pricing(500, _Pricing(taxValue=50, serviceCharge=25, deliveryFee=100), ALL_ALLOWED)
        self.assertEqual(pricing["total"], 675)

    def test_discount_larger_than_the_subtotal_is_refused(self):
        with self.assertRaises(HTTPException) as context:
            _compute_pricing(100, _Pricing(discountValue=150), ALL_ALLOWED)
        self.assertEqual(context.exception.status_code, 422)

    def test_a_cashier_without_the_discount_grant_cannot_apply_one(self):
        with self.assertRaises(HTTPException) as context:
            _compute_pricing(100, _Pricing(discountValue=10), {"canApplyDiscount": False})
        self.assertEqual(context.exception.status_code, 403)

    def test_a_zero_discount_is_allowed_even_without_the_grant(self):
        pricing = _compute_pricing(100, _Pricing(), {"canApplyDiscount": False})
        self.assertEqual(pricing["total"], 100)


class CashierOrderInputTests(unittest.TestCase):
    def test_every_advertised_payment_method_is_accepted(self):
        for code in CASHIER_PAYMENT_METHODS:
            self.assertEqual(_normalize_payment_method(code), code)

    def test_an_unknown_payment_method_is_refused(self):
        with self.assertRaises(HTTPException) as context:
            _normalize_payment_method("crypto")
        self.assertEqual(context.exception.status_code, 422)

    def test_dine_in_needs_no_address_but_delivery_does(self):
        self.assertEqual(_build_fulfillment("dine_in", {})["type"], "none")
        with self.assertRaises(HTTPException):
            _build_fulfillment("delivery", {"line1": "", "city": ""})
        delivery = _build_fulfillment("delivery", {"line1": "12 Mall Road", "city": "Lahore"})
        self.assertEqual(delivery["address"]["city"], "Lahore")
        self.assertEqual(delivery["serviceType"], "delivery")

    def test_service_type_is_validated(self):
        self.assertEqual(_normalize_service_type("Dine-In"), "dine_in")
        with self.assertRaises(HTTPException):
            _normalize_service_type("teleport")


class CashierOrderViewTests(unittest.TestCase):
    def setUp(self):
        self.transaction = {
            "_id": ObjectId(),
            "tenantId": ObjectId(),
            "transactionNumber": "ORD-20260915-00001",
            "status": "completed",
            "receiptToken": "abc123token",
            "items": [{"itemId": ObjectId(), "name": "Shirt", "quantity": 1, "unitPrice": 2000, "subtotal": 2000, "costPrice": 900, "stockSnapshot": {"availableQuantity": 4}}],
            "pricing": {"subtotal": 2000, "total": 2000},
            "cashier": {"cashierId": ObjectId(), "userId": ObjectId(), "name": "Ali", "employeeCode": "C-1"},
            "internalNotes": "owner only",
            "inventoryStatus": "deducted",
            "statusHistory": [{"field": "status", "to": "completed"}],
        }

    def test_margin_and_stock_levels_never_reach_a_receipt(self):
        view = cashier_order_view(self.transaction)
        self.assertNotIn("costPrice", view["items"][0])
        self.assertNotIn("stockSnapshot", view["items"][0])

    def test_internal_workflow_fields_are_dropped(self):
        view = cashier_order_view(self.transaction)
        for field in ("internalNotes", "inventoryStatus", "statusHistory", "tenantId"):
            self.assertNotIn(field, view)

    def test_database_identifiers_are_not_exposed_in_the_cashier_block(self):
        view = cashier_order_view(self.transaction)
        self.assertEqual(view["cashier"], {"name": "Ali", "employeeCode": "C-1"})

    def test_the_receipt_token_is_the_only_handle_and_the_row_id_never_leaves(self):
        view = cashier_order_view(self.transaction)
        self.assertEqual(view["receiptToken"], "abc123token")
        self.assertNotIn("id", view)
        self.assertNotIn(str(self.transaction["_id"]), repr(view))


class ImportHeaderTests(unittest.TestCase):
    def test_common_spreadsheet_spellings_all_map_to_one_key(self):
        for header in ("Order Number", "order no", "Invoice No", "ORDER ID", "orderNumber"):
            self.assertEqual(normalize_import_header(header), "orderNumber", header)

    def test_an_unknown_header_maps_to_nothing_rather_than_guessing(self):
        self.assertEqual(normalize_import_header("Salesman Commission %"), "")

    def test_every_advertised_column_round_trips(self):
        for column in import_column_guide():
            self.assertEqual(normalize_import_header(column["label"]), column["key"])


class ImportValueTests(unittest.TestCase):
    def test_the_common_pakistani_and_iso_date_formats_are_read(self):
        for value in ("2025-03-18", "18/03/2025", "18-Mar-2025", "2025-03-18 14:30"):
            self.assertEqual(parse_import_date(value).date().isoformat(), "2025-03-18", value)

    def test_an_unreadable_date_returns_none_rather_than_today(self):
        self.assertIsNone(parse_import_date("last tuesday"))

    def test_a_naive_datetime_is_pinned_to_utc(self):
        self.assertEqual(parse_import_date(datetime(2025, 3, 18)).tzinfo, timezone.utc)

    def test_status_words_map_onto_the_platform_vocabulary(self):
        self.assertEqual(map_payment_status("Paid"), "paid")
        self.assertEqual(map_payment_status("Cash on Delivery"), "cod")
        self.assertEqual(map_payment_status("Due"), "unpaid")
        self.assertEqual(map_order_status("Delivered"), "completed")
        self.assertEqual(map_order_status("Canceled"), "cancelled")

    def test_an_unrecognized_status_falls_back_to_a_closed_sale(self):
        self.assertEqual(map_order_status("shipped via TCS"), "completed")


class ImportParsingTests(unittest.TestCase):
    HEADERS = ["Order No", "Date", "Customer", "Phone", "Item", "Qty", "Rate", "Total", "Payment", "Status"]

    def test_repeated_order_numbers_group_into_one_multi_line_order(self):
        rows = [
            ["INV-1", "2025-03-18", "Sara", "03001234567", "Shirt", 2, 1500, 3000, "Cash", "Completed"],
            ["INV-1", "2025-03-18", "Sara", "03001234567", "Cap", 1, 500, 500, "Cash", "Completed"],
            ["INV-2", "2025-03-19", "Bilal", "03007654321", "Shoes", 1, 4000, 4000, "Card", "Completed"],
        ]
        orders, errors, mapping = _parse_rows(self.HEADERS, rows)
        self.assertEqual(errors, [])
        self.assertEqual(len(orders), 2)
        self.assertEqual(len(orders[0]["items"]), 2)
        self.assertEqual(orders[0]["subtotal"], 3500)
        self.assertEqual(orders[0]["totalAmount"], 3500)
        self.assertEqual(mapping["Order No"], "orderNumber")

    def test_rows_without_an_order_number_stay_separate_orders(self):
        rows = [
            ["", "2025-03-18", "Sara", "", "Shirt", 1, 1500, 1500, "", ""],
            ["", "2025-03-18", "Bilal", "", "Cap", 1, 500, 500, "", ""],
        ]
        orders, _, _ = _parse_rows(self.HEADERS, rows)
        self.assertEqual(len(orders), 2)

    def test_a_line_total_without_a_rate_still_yields_a_unit_price(self):
        rows = [["INV-9", "2025-03-18", "Sara", "", "Bulk lot", 4, "", 2000, "", ""]]
        orders, _, _ = _parse_rows(self.HEADERS, rows)
        self.assertEqual(orders[0]["items"][0]["unitPrice"], 500)

    def test_an_unreadable_date_fails_only_its_own_row(self):
        rows = [
            ["INV-1", "not a date", "Sara", "", "Shirt", 1, 1500, 1500, "", ""],
            ["INV-2", "2025-03-19", "Bilal", "", "Cap", 1, 500, 500, "", ""],
        ]
        orders, errors, _ = _parse_rows(self.HEADERS, rows)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["row"], 2)
        self.assertEqual(len(orders), 1)

    def test_an_empty_row_is_reported_rather_than_imported_as_a_zero_order(self):
        rows = [["", "", "", "", "", "", "", "", "", ""]]
        orders, errors, _ = _parse_rows(self.HEADERS, rows)
        self.assertEqual(orders, [])
        self.assertEqual(len(errors), 1)

    def test_negative_amounts_are_refused(self):
        rows = [["INV-1", "2025-03-18", "Sara", "", "Refund", 1, -500, -500, "", ""]]
        orders, errors, _ = _parse_rows(self.HEADERS, rows)
        self.assertEqual(orders, [])
        self.assertIn("negative", errors[0]["message"].lower())

    def test_a_sheet_with_no_recognizable_headers_is_refused_outright(self):
        with self.assertRaises(HTTPException) as context:
            _parse_rows(["aaa", "bbb"], [["1", "2"]])
        self.assertEqual(context.exception.status_code, 422)

    def test_currency_symbols_and_thousands_separators_are_read_as_numbers(self):
        rows = [["INV-1", "2025-03-18", "Sara", "", "Shirt", "2", "Rs 1,500.50", "PKR 3,001.00", "", ""]]
        orders, errors, _ = _parse_rows(self.HEADERS, rows)
        self.assertEqual(errors, [])
        self.assertEqual(orders[0]["items"][0]["unitPrice"], 1500.5)
        self.assertEqual(orders[0]["totalAmount"], 3001.0)

    def test_a_stated_total_that_disagrees_with_the_arithmetic_is_flagged_not_silently_changed(self):
        rows = [["INV-1", "2025-03-18", "Sara", "", "Shirt", 1, 1000, 9999, "", ""]]
        orders, _, _ = _parse_rows(self.HEADERS, rows)
        self.assertEqual(orders[0]["totalAmount"], 9999)
        self.assertTrue(orders[0]["totalMismatch"])


class ImportDuplicateTests(unittest.TestCase):
    def test_the_fingerprint_ignores_formatting_of_name_and_phone(self):
        first = {"orderDate": "2025-03-18T00:00:00+00:00", "customerName": " Sara  Khan ", "customerPhone": "+92 300 1234567", "totalAmount": 3500}
        second = {"orderDate": "2025-03-18", "customerName": "sara khan", "customerPhone": "923001234567", "totalAmount": 3500.0}
        self.assertEqual(_fingerprint(first), _fingerprint(second))

    def test_a_different_amount_is_a_different_order(self):
        base = {"orderDate": "2025-03-18", "customerName": "Sara", "customerPhone": "03001234567", "totalAmount": 3500}
        other = {**base, "totalAmount": 3600}
        self.assertNotEqual(_fingerprint(base), _fingerprint(other))


class CashierAuthBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_cashier_token_is_refused_by_the_owner_dependency(self):
        from app.core.security import get_current_business_user

        with self.assertRaises(HTTPException) as context:
            await get_current_business_user({"accountType": "cashier", "tenantId": ObjectId()})
        self.assertEqual(context.exception.status_code, 403)

    async def test_an_owner_token_is_refused_by_the_cashier_dependency(self):
        from app.core.security import get_current_cashier_user

        with self.assertRaises(HTTPException) as context:
            await get_current_cashier_user({"accountType": "business_owner"})
        self.assertEqual(context.exception.status_code, 403)

    async def test_a_cashier_with_no_business_is_refused(self):
        from app.core.security import get_current_cashier_user

        with self.assertRaises(HTTPException) as context:
            await get_current_cashier_user({"accountType": "cashier"})
        self.assertEqual(context.exception.status_code, 403)

    async def test_context_lookup_is_scoped_to_the_account_tenant_and_active_flag(self):
        from app.services import cashier_service

        tenant_id = ObjectId()
        user_id = ObjectId()
        cashiers = AsyncMock()
        cashiers.find_one.return_value = {"_id": ObjectId(), "tenantId": tenant_id, "userId": user_id, "fullName": "Ali"}
        tenants = AsyncMock()
        tenants.find_one.return_value = {"_id": tenant_id, "name": "Business A"}
        fake_db = type("FakeDb", (), {"cashiers": cashiers, "tenants": tenants})()

        with patch.object(cashier_service, "get_database", return_value=fake_db), patch.object(
            cashier_service, "ensure_tenant_module_enabled", new=AsyncMock()
        ):
            cashier, tenant = await cashier_service.get_cashier_context({"_id": user_id, "tenantId": tenant_id})

        cashiers.find_one.assert_awaited_once_with({"tenantId": tenant_id, "userId": user_id, "isActive": True})
        self.assertEqual(tenant["name"], "Business A")
        self.assertEqual(cashier["fullName"], "Ali")

    async def test_a_deactivated_cashier_cannot_resolve_a_business(self):
        from app.services import cashier_service

        cashiers = AsyncMock()
        cashiers.find_one.return_value = None
        fake_db = type("FakeDb", (), {"cashiers": cashiers, "tenants": AsyncMock()})()

        with patch.object(cashier_service, "get_database", return_value=fake_db):
            with self.assertRaises(HTTPException) as context:
                await cashier_service.get_cashier_context({"_id": ObjectId(), "tenantId": ObjectId()})
        self.assertEqual(context.exception.status_code, 403)


class CashierModuleWiringTests(unittest.TestCase):
    def test_the_cashier_module_is_seeded_so_owners_can_enable_it(self):
        from app.db.seeders.seed_modules import DEFAULT_MODULES

        module = next(row for row in DEFAULT_MODULES if row["code"] == "cashier")
        self.assertIn("items", module["dependencies"])
        self.assertIn("/dashboard/cashiers", module["frontendRoutes"])

    def test_the_business_login_accepts_both_workspace_roles(self):
        import inspect

        from app.api.v1 import auth_routes

        source = inspect.getsource(auth_routes)
        self.assertIn('expected_account_type={"business_owner", "cashier"}', source)


class ManualLineInventoryTests(unittest.IsolatedAsyncioTestCase):
    """A line with no catalog row behind it must not reach the stock machinery.

    Before this, ``_line_item_id`` turned a manual line's empty ``itemId`` into a 400,
    which would have made every all-manual counter sale fail at the inventory step.
    """

    async def test_manual_and_imported_lines_move_no_stock_and_do_not_error(self):
        from app.services import inventory_service

        transaction_id = ObjectId()
        tenant_id = ObjectId()
        stored = {
            "_id": transaction_id,
            "tenantId": tenant_id,
            "transactionType": "order",
            "items": [
                {"itemId": None, "name": "Repair charge", "quantity": 1, "isCustomItem": True},
                {"name": "Imported line", "quantity": 2, "isCustomItem": True},
            ],
        }
        transactions = AsyncMock()
        transactions.find_one.return_value = stored
        transactions.update_one.return_value = type("R", (), {"matched_count": 1})()
        items = AsyncMock()
        fake_db = type("FakeDb", (), {"transactions": transactions, "items": items})()

        with patch.object(inventory_service, "get_database", return_value=fake_db):
            await inventory_service.deduct_transaction_stock(stored, ObjectId())

        items.find_one.assert_not_awaited()
        applied = transactions.update_one.await_args_list[-1].args[1]
        self.assertEqual(applied["$set"]["inventoryStatus"], "not_required")


class CustomerSourceTagTests(unittest.TestCase):
    def test_counter_and_imported_customers_are_tagged_by_where_they_came_from(self):
        from app.services.customer_service import _customer_source_tag

        self.assertEqual(_customer_source_tag("cashier"), "cashier")
        self.assertEqual(_customer_source_tag("imported"), "imported")
        self.assertEqual(_customer_source_tag("customer_portal"), "customer_portal")

    def test_an_unknown_source_still_falls_back_to_website(self):
        from app.services.customer_service import _customer_source_tag

        self.assertEqual(_customer_source_tag(None), "website")
        self.assertEqual(_customer_source_tag("some_new_channel"), "website")


if __name__ == "__main__":
    unittest.main()
