import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.services.customer_portal_service import _build_transaction_from_items


class CustomerPortalServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_transaction_ignores_legacy_invalid_customer_phone(self):
        tenant_id = ObjectId()
        item_id = ObjectId()
        user_id = ObjectId()
        profile_id = ObjectId()
        inserted_id = ObjectId()
        
        class AsyncCursor:
            def __init__(self, items):
                self._items = items

            def __aiter__(self):
                self._iterator = iter(self._items)
                return self

            async def __anext__(self):
                try:
                    return next(self._iterator)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        fake_items = type(
            "ItemsCollection",
            (),
            {
                "find": lambda self, query: AsyncCursor([
                    {
                        "_id": item_id,
                        "tenantId": tenant_id,
                        "status": "active",
                        "name": "Zinger Burger",
                        "price": 650,
                        "isSellable": True,
                        "isBookable": False,
                    }
                ]),
            },
        )()
        fake_transactions = type(
            "TransactionsCollection",
            (),
            {
                "insert_one": AsyncMock(return_value=type("InsertResult", (), {"inserted_id": inserted_id})()),
            },
        )()
        fake_db = type("FakeDb", (), {"items": fake_items, "transactions": fake_transactions})()
        tenant = {"_id": tenant_id, "name": "OverDose", "slug": "overdose"}
        current_user = {"_id": user_id, "fullName": "Danyal Khan", "email": "danyal@gmail.com", "phone": "bad-phone"}
        profile = {"_id": profile_id, "phone": "bad-phone"}

        with (
            patch("app.services.customer_portal_service.get_database", return_value=fake_db),
            patch("app.services.customer_portal_service.validate_tenant_fulfillment"),
            patch("app.services.customer_portal_service.validate_custom_values_for_tenant_oid", AsyncMock(return_value={"valid": True, "values": {}})),
            patch("app.services.customer_portal_service.generate_transaction_number", AsyncMock(return_value="ORD-0001")),
            patch("app.services.customer_portal_service.sync_customer_stats_for_transaction", AsyncMock(return_value=ObjectId())),
            patch("app.services.customer_portal_service.create_business_notification", AsyncMock()),
            patch("app.services.customer_portal_service.create_customer_notification", AsyncMock()),
            patch("app.services.customer_portal_service.reserve_transaction_stock", AsyncMock(side_effect=lambda transaction, user_id=None: transaction)),
            patch(
                "app.services.customer_portal_service.get_customer_payment_options_for_tenant",
                AsyncMock(
                    return_value={
                        "enabled": True,
                        "defaultMethod": "cod",
                        "methods": [{"code": "cod", "label": "Cash on Delivery", "requiresOwnerApproval": False}],
                        "customerInstructions": "Pay with COD.",
                    }
                ),
            ),
        ):
            transaction = await _build_transaction_from_items(
                tenant,
                [{"itemId": str(item_id), "quantity": 2}],
                {"type": "none"},
                "",
                {},
                current_user,
                profile,
                "customer_portal",
                "order",
            )

        self.assertEqual(transaction["customerSnapshot"]["phone"], "")
        self.assertEqual(transaction["pricing"]["total"], 1300.0)
        fake_transactions.insert_one.assert_awaited_once()
