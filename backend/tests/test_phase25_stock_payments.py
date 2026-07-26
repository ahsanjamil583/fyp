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
)
from app.services.transaction_service import update_transaction


class Phase25StockPaymentsTests(unittest.IsolatedAsyncioTestCase):
    async def test_payment_foundation_normalizes_local_method_and_status_aliases(self):
        self.assertEqual(_normalize_method("bank_transfer"), "manual_bank")
        self.assertEqual(_normalize_method("JazzCash"), "jazzcash_mock")
        self.assertEqual(_normalize_method("easypaisa"), "easypaisa_mock")
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
        self.assertEqual(options["defaultMethod"], "jazzcash_mock")
        jazzcash = next(method for method in options["methods"] if method["code"] == "jazzcash_mock")
        self.assertEqual(jazzcash["accountNumber"], "03000000000")
        self.assertTrue(jazzcash["requiresOwnerApproval"])

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
                find_one=AsyncMock(return_value={**transaction, "inventoryStatus": "released"}),
            ),
            inventory_movements=SimpleNamespace(
                insert_one=AsyncMock(return_value=SimpleNamespace(inserted_id=ObjectId()))
            ),
        )

        with patch("app.services.inventory_service.get_database", return_value=fake_db):
            updated = await restore_transaction_stock(transaction, user_id)

        fake_db.items.update_one.assert_awaited_once()
        update_doc = fake_db.items.update_one.await_args.args[1]
        self.assertEqual(update_doc["$set"]["variants.0.stockQuantity"], 7.0)
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
