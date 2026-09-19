import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.services.inventory_service import apply_transaction_inventory_transition, restore_transaction_stock
from app.services.payment_service import (
    _normalize_method,
    _normalize_record_status,
    _payment_status_from_summary,
    normalize_customer_payment_preference,
    refund_transaction_payment,
    serialize_customer_payment_options,
    _method_customer_details,
)
from app.services.transaction_service import update_transaction


class Phase25StockPaymentsTests(unittest.IsolatedAsyncioTestCase):
    async def test_payment_foundation_normalizes_local_method_and_status_aliases(self):
        self.assertEqual(_normalize_method("bank_transfer"), "manual_bank")
        # "jazzcash"/"easypaisa" now name the redirect gateways; the *_mock codes remain
        # valid for the owner-verified manual flow and for historical records.
        self.assertEqual(_normalize_method("JazzCash"), "jazzcash")
        self.assertEqual(_normalize_method("easypaisa"), "easypaisa")
        self.assertEqual(_normalize_method("jazzcash_mock"), "jazzcash_mock")
        self.assertEqual(_normalize_record_status("completed"), "paid")
        self.assertEqual(_normalize_record_status("pending"), "pending_verification")
        self.assertEqual(_normalize_record_status("failed"), "rejected")

    async def test_payment_status_from_summary_supports_cod_and_pending_verification(self):
        transaction = {"transactionType": "order", "paymentStatus": "unpaid"}

        self.assertEqual(
            _payment_status_from_summary(transaction, {"total": 100, "paid": 0, "pending": 0, "cod": 100, "rejected": 0, "refunded": 0, "balance": 100}),
            "cod",
        )
        self.assertEqual(
            _payment_status_from_summary(transaction, {"total": 100, "paid": 0, "pending": 100, "cod": 0, "rejected": 0, "refunded": 0, "balance": 100}),
            "pending_verification",
        )
        self.assertEqual(
            _payment_status_from_summary(transaction, {"total": 100, "paid": 0, "pending": 0, "cod": 0, "rejected": 100, "refunded": 0, "balance": 100}),
            "rejected",
        )

    async def test_customer_payment_options_include_local_method_details(self):
        options = serialize_customer_payment_options(
            {
                "codEnabled": True,
                "manualEnabled": True,
                "bankTransferEnabled": True,
                "jazzCashEnabled": True,
                "easyPaisaEnabled": False,
                "paymentsDemoMode": True,
                "requireOwnerApproval": True,
                "defaultMethod": "jazzcash_mock",
                "customerInstructions": "Send reference after payment.",
                "bankName": "Meezan",
                "bankAccountTitle": "BizXus Demo",
                "bankAccountNumber": "12345",
                "bankIban": "PK00TEST",
                "jazzCashNumber": "03000000000",
                "jazzCashAccountTitle": "BizXus Wallet",
            }
        )

        self.assertTrue(options["enabled"])
        # With the gateway available this tenant is offered the redirect flow, and its
        # saved "jazzcash_mock" default carries over to it rather than dropping to COD.
        self.assertEqual(options["defaultMethod"], "jazzcash")
        jazzcash = next(method for method in options["methods"] if method["code"] == "jazzcash")
        self.assertTrue(jazzcash["isOnline"])
        self.assertFalse(jazzcash["requiresOwnerApproval"])

        manual = _method_customer_details(
            {"jazzCashNumber": "03000000000", "jazzCashAccountTitle": "BizXus Wallet"}, "jazzcash_mock"
        )
        self.assertEqual(manual["accountNumber"], "03000000000")
        self.assertTrue(manual["requiresOwnerApproval"])

    async def test_customer_payment_preference_rejects_disabled_method(self):
        options = {
            "defaultMethod": "cod",
            "methods": [{"code": "cod", "label": "Cash on Delivery", "requiresOwnerApproval": False}],
            "customerInstructions": "COD only.",
        }

        preference = normalize_customer_payment_preference(None, options)
        self.assertEqual(preference["method"], "cod")
        with self.assertRaises(Exception):
            normalize_customer_payment_preference("jazzcash_mock", options)

    async def test_restore_transaction_stock_reverses_deducted_variant_inventory(self):
        tenant_id = ObjectId()
        transaction_id = ObjectId()
        item_id = ObjectId()
        user_id = ObjectId()
        variant_id = ObjectId()

        transaction = {
            "_id": transaction_id,
            "tenantId": tenant_id,
            "transactionType": "order",
            "inventoryStatus": "deducted",
            "items": [
                {
                    "itemId": item_id,
                    "quantity": 2,
                    "selectedVariantIndex": 0,
                    "selectedVariantName": "Black / Large",
                    "selectedOptions": {"color": "Black", "size": "Large"},
                    "variantSku": "BLK-L",
                    "stockSnapshot": {"tracked": True},
                }
            ],
        }
        item = {
            "_id": item_id,
            "tenantId": tenant_id,
            "status": "active",
            "name": "Hoodie",
            "itemType": "product",
            "isStockTracked": True,
            "variants": [
                {
                    "name": "Black / Large",
                    "sku": "BLK-L",
                    "price": 2500,
                    "stockQuantity": 5,
                    "reservedQuantity": 0,
                    "isActive": True,
                }
            ],
        }

        fake_db = SimpleNamespace(
            items=SimpleNamespace(find_one=AsyncMock(return_value=item), update_one=AsyncMock()),
            transactions=SimpleNamespace(
                update_one=AsyncMock(),
                find_one=AsyncMock(side_effect=[transaction, {**transaction, "inventoryStatus": "released"}]),
            ),
            inventory_movements=SimpleNamespace(
                insert_one=AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))
            ),
        )

        with patch("app.services.inventory_service.get_database", return_value=fake_db):
            updated = await restore_transaction_stock(transaction, user_id)

        fake_db.items.update_one.assert_awaited_once()
        update_doc = fake_db.items.update_one.await_args.args[1]
        self.assertEqual(update_doc["$inc"]["variants.0.stockQuantity"], 2.0)
        self.assertNotIn("variants.0.reservedQuantity", update_doc["$inc"])
        self.assertEqual(updated["inventoryStatus"], "released")

    async def test_apply_transaction_inventory_transition_restores_on_rejected(self):
        previous = {"status": "pending", "transactionType": "order"}
        updated = {"status": "rejected", "transactionType": "order", "inventoryStatus": "reserved"}

        with patch("app.services.inventory_service.restore_transaction_stock", AsyncMock(return_value={"status": "rejected"})) as restore_mock:
            result = await apply_transaction_inventory_transition(previous, updated, ObjectId())

        restore_mock.assert_awaited_once()
        self.assertEqual(result["status"], "rejected")

    async def test_refund_transaction_payment_restores_stock_when_fully_refunded(self):
        tenant_id = ObjectId()
        transaction_id = ObjectId()
        user_id = ObjectId()
        item_id = ObjectId()

        transaction = {
            "_id": transaction_id,
            "tenantId": tenant_id,
            "transactionType": "order",
            "transactionNumber": "ORD-1001",
            "status": "completed",
            "inventoryStatus": "deducted",
            "paymentStatus": "paid",
            "pricing": {"total": 100.0},
            "items": [{"itemId": item_id, "quantity": 1, "currency": "PKR"}],
            "customerSnapshot": {"name": "Ali", "phone": "03001234567"},
        }
        updated_transaction = {**transaction, "paymentStatus": "refunded"}

        fake_db = SimpleNamespace(
            payment_records=SimpleNamespace(insert_one=AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))),
            transactions=SimpleNamespace(update_one=AsyncMock(), find_one=AsyncMock(return_value=updated_transaction)),
        )

        refund_payload = SimpleNamespace(amount=100, method="manual", referenceNumber="REF-1", notes="Returned")

        with (
            patch("app.services.payment_service.get_database", return_value=fake_db),
            patch("app.services.payment_service._ensure_payment_access", AsyncMock(return_value=(tenant_id, {"_id": tenant_id, "slug": "demo"}))),
            patch("app.services.payment_service._get_transaction_or_404", AsyncMock(return_value=transaction)),
            patch("app.services.payment_service._calculate_payment_summary", AsyncMock(side_effect=[
                {"total": 100.0, "paid": 100.0, "pending": 0.0, "refunded": 0.0, "balance": 0.0},
                {"total": 100.0, "paid": 0.0, "pending": 0.0, "refunded": 100.0, "balance": 0.0},
            ])),
            patch("app.services.payment_service.restore_transaction_stock", AsyncMock(return_value={**updated_transaction, "inventoryStatus": "released"})) as restore_mock,
            patch("app.services.payment_service.create_business_notification", AsyncMock()),
        ):
            result = await refund_transaction_payment(str(tenant_id), str(transaction_id), refund_payload, {"_id": user_id})

        restore_mock.assert_awaited_once()
        self.assertEqual(result["transaction"]["paymentStatus"], "refunded")

    async def test_update_transaction_restores_stock_when_payment_status_set_to_refunded(self):
        tenant_id = ObjectId()
        transaction_id = ObjectId()
        user_id = ObjectId()
        existing = {
            "_id": transaction_id,
            "tenantId": tenant_id,
            "transactionType": "order",
            "transactionNumber": "ORD-2001",
            "status": "completed",
            "inventoryStatus": "deducted",
            "paymentStatus": "paid",
            "pricing": {"total": 250.0},
            "items": [],
            "customerId": None,
        }
        updated = {**existing, "paymentStatus": "refunded"}

        fake_db = SimpleNamespace(
            transactions=SimpleNamespace(
                find_one=AsyncMock(side_effect=[existing, updated]),
                update_one=AsyncMock(),
            )
        )
        payload = SimpleNamespace(status=None, paymentStatus="refunded", internalNotes="")

        with (
            patch("app.services.transaction_service.get_database", return_value=fake_db),
            patch("app.services.transaction_service._ensure_transaction_access", AsyncMock(return_value=(tenant_id, {"_id": tenant_id, "name": "Demo"}))),
            patch("app.services.transaction_service.create_business_notification", AsyncMock()),
            patch("app.services.transaction_service.sync_customer_stats_for_transaction", AsyncMock()),
            patch("app.services.transaction_service.restore_transaction_stock", AsyncMock(return_value={**updated, "inventoryStatus": "released"})) as restore_mock,
            patch("app.services.transaction_service.apply_transaction_inventory_transition", AsyncMock(return_value=updated)),
            patch("app.services.transaction_service.get_inventory_movements_for_transaction", AsyncMock(return_value=[])),
        ):
            result = await update_transaction(str(tenant_id), str(transaction_id), payload, {"_id": user_id})

        restore_mock.assert_awaited_once()
        self.assertEqual(result["paymentStatus"], "refunded")


if __name__ == "__main__":
    unittest.main()


class PaymentSummaryRoundingTests(unittest.IsolatedAsyncioTestCase):
    """Money summed as raw floats left balances like 1e-14.

    That reported a fully paid order as partially paid, and Stripe then floored the
    "remaining" amount to a one-paisa charge.
    """

    async def _summary(self, records, total):
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.services import payment_service

        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=records)
        db = MagicMock()
        db.payment_records.find = MagicMock(return_value=cursor)
        with patch.object(payment_service, "get_database", return_value=db):
            return await payment_service._calculate_payment_summary(
                ObjectId(), {"_id": ObjectId(), "pricing": {"total": total}}
            )

    async def test_three_float_payments_close_the_order_exactly(self):
        records = [
            {"recordType": "payment", "status": "paid", "amount": 0.1},
            {"recordType": "payment", "status": "paid", "amount": 0.2},
            {"recordType": "payment", "status": "paid", "amount": 0.3},
        ]
        summary = await self._summary(records, 0.6)
        self.assertEqual(summary["paid"], 0.6)
        self.assertEqual(summary["balance"], 0.0, "0.1 + 0.2 + 0.3 must not leave a residue")

    async def test_a_genuine_balance_survives(self):
        records = [{"recordType": "payment", "status": "paid", "amount": 400.0}]
        summary = await self._summary(records, 1000.0)
        self.assertEqual(summary["balance"], 600.0)


class CustomerPaymentRecordPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_decision_notes_never_reach_the_customer(self):
        """The owner writes these for their own records. They used to be returned on
        the customer's own order page."""
        from unittest.mock import MagicMock, patch

        from app.services import payment_service

        record = {
            "_id": ObjectId(),
            "transactionId": ObjectId(),
            "amount": 100,
            "status": "paid",
            "ownerDecisionNotes": "Customer argued about this one, watch them.",
            "internalNotes": "internal",
            "verification": {
                "verifiedByUserId": ObjectId(),
                "decisionNotes": "approved reluctantly",
                "verifiedAt": None,
            },
        }

        class Cursor:
            def __aiter__(self):
                self._done = False
                return self

            async def __anext__(self):
                if self._done:
                    raise StopAsyncIteration
                self._done = True
                return record

        find = MagicMock()
        find.sort = MagicMock(return_value=Cursor())
        db = MagicMock()
        db.payment_records.find = MagicMock(return_value=find)
        with patch.object(payment_service, "get_database", return_value=db):
            rows = await payment_service.list_customer_payment_records_for_transaction({"_id": ObjectId()})

        self.assertEqual(len(rows), 1)
        self.assertNotIn("ownerDecisionNotes", rows[0])
        self.assertNotIn("internalNotes", rows[0])
        self.assertNotIn("verifiedByUserId", rows[0].get("verification", {}))
        self.assertNotIn("decisionNotes", rows[0].get("verification", {}))


class PaymentRecordAudienceTests(unittest.TestCase):
    """The payment summary is rendered on BOTH the customer's order page and the owner's
    transactions and payments screens. Stripping it unconditionally removed the owner's
    own decision notes from their own UI."""

    def test_the_summary_strips_only_for_the_customer(self):
        import inspect

        from app.services import payment_service

        signature = inspect.signature(payment_service.summarize_payment_records_for_transaction)
        self.assertIn("for_customer", signature.parameters)
        self.assertFalse(signature.parameters["for_customer"].default, "owners must see their own notes by default")

    def test_the_customer_portal_asks_for_the_stripped_form(self):
        import inspect

        from app.services import customer_portal_service

        source = inspect.getsource(customer_portal_service)
        self.assertEqual(source.count("for_customer=True"), 2, "both customer order views must strip")

    def test_all_three_customer_serializers_share_one_strip_list(self):
        """A third serializer kept its own shorter list, which is how the owner's notes
        kept reaching the customer after the other two were fixed."""
        import inspect

        from app.core import private_uploads

        self.assertIn("_customer_safe_payment_record", inspect.getsource(private_uploads.customer_payment_result))


class UniqueIndexFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_failed_unique_index_is_not_swallowed(self):
        """Swallowing it leaves the collection with no uniqueness while the application
        carries on assuming there is some, which is how a duplicate account slips in."""
        from unittest.mock import AsyncMock, MagicMock

        from app.db.indexes import _ensure_index

        collection = MagicMock()
        collection.name = "users"
        collection.create_index = AsyncMock(side_effect=RuntimeError("duplicate key"))
        with self.assertRaises(RuntimeError):
            await _ensure_index(collection, "email", unique=True, sparse=True)

    async def test_a_failed_ordinary_index_is_tolerated(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.db.indexes import _ensure_index

        collection = MagicMock()
        collection.name = "items"
        collection.create_index = AsyncMock(side_effect=RuntimeError("spec changed"))
        await _ensure_index(collection, "createdAt")


class CustomerReceiptPrivacyTests(unittest.TestCase):
    """The receipt HTML was the fifth customer-facing payment serializer, and the only
    one still rendering `notes` - which is where the provider's raw failure text lands."""

    RECORD = {
        "_id": "r1",
        "amount": 500,
        "currency": "PKR",
        "method": "stripe_test",
        "status": "failed",
        "notes": "Stripe: declined for account acct_12345 param source[number]",
        "ownerDecisionNotes": "this customer argues a lot",
        "verification": {"decisionNotes": "approved reluctantly", "verifiedByUserId": "u1"},
        "createdAt": None,
    }

    def test_the_customer_copy_hides_provider_and_owner_detail(self):
        from app.services.payment_service import _build_payment_receipt_html, _customer_safe_payment_record

        html = _build_payment_receipt_html(
            {"name": "Shop"}, {"transactionNumber": "T1", "pricing": {"total": 500}},
            _customer_safe_payment_record(dict(self.RECORD)),
        )
        for secret in ("acct_12345", "argues a lot", "reluctantly"):
            self.assertNotIn(secret, html, secret)

    def test_the_owner_copy_still_shows_everything(self):
        """The owner writes these notes for themselves; hiding them from the owner was a
        regression introduced while fixing the customer leak."""
        from app.services.payment_service import _build_payment_receipt_html

        html = _build_payment_receipt_html(
            {"name": "Shop"}, {"transactionNumber": "T1", "pricing": {"total": 500}}, dict(self.RECORD)
        )
        self.assertIn("acct_12345", html)

    def test_the_customer_route_passes_the_stripped_record(self):
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service.get_customer_payment_receipt_html)
        self.assertIn("_customer_safe_payment_record(record)", source)
        owner = inspect.getsource(payment_service.get_owner_payment_receipt_html)
        self.assertNotIn("_customer_safe_payment_record", owner)


class CodReconciliationTests(unittest.TestCase):
    def test_the_owner_entry_measures_cod_against_its_own_bucket(self):
        """COD does not reduce `balance`, so comparing a COD entry against the balance
        made an existing COD record invisible and allowed the full total twice."""
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service.record_transaction_payment)
        self.assertIn('if record_status == "cod":', source)
        self.assertIn('current_summary["cod"]', source)

    def test_the_importer_covers_refunded(self):
        import inspect

        from app.services import order_import_service

        source = inspect.getsource(order_import_service)
        self.assertIn('{"paid", "cod", "refunded"}', source)
