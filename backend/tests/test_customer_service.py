import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.services.customer_service import ensure_customer_record_for_tenant, sync_registered_customer_records


class CustomerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_customer_record_for_tenant_reuses_transaction_shape(self):
        tenant_id = ObjectId()
        user_id = ObjectId()
        profile_id = ObjectId()

        with patch("app.services.customer_service.find_or_create_customer_from_transaction", AsyncMock(return_value=ObjectId())) as find_mock:
            await ensure_customer_record_for_tenant(
                {"_id": tenant_id},
                customer_user_id=user_id,
                customer_profile_id=profile_id,
                name="Danyal Khan",
                phone="03001234567",
                email="danyal@gmail.com",
                address={"line1": "street 2", "city": "Attock"},
                source_tag="customer_portal",
            )

        find_mock.assert_awaited_once()
        self.assertEqual(find_mock.await_args.kwargs["customer_user_id"], user_id)
        self.assertEqual(find_mock.await_args.kwargs["customer_profile_id"], profile_id)

    async def test_sync_registered_customer_records_updates_guest_and_linked_matches(self):
        linked_id = ObjectId()
        user_id = ObjectId()

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

        fake_customers = type(
            "Customers",
            (),
            {
                "find": lambda self, query: AsyncCursor(
                    [
                        {
                            "_id": ObjectId(),
                            "customerUserId": None,
                            "name": "Guest Customer",
                            "phone": "03001234567",
                            "email": "",
                            "address": {},
                            "status": "active",
                            "tags": ["website"],
                        },
                        {
                            "_id": linked_id,
                            "customerUserId": user_id,
                            "name": "Old Name",
                            "phone": "03001111111",
                            "email": "old@example.com",
                            "address": {"line1": "old", "city": "old"},
                            "status": "inactive",
                            "tags": [],
                        },
                    ]
                ),
                "update_one": AsyncMock(),
            },
        )()
        fake_db = type("FakeDb", (), {"customers": fake_customers})()

        with patch("app.services.customer_service.get_database", return_value=fake_db):
            updated_count = await sync_registered_customer_records(
                customer_user_id=user_id,
                name="Danyal Khan",
                phone="03001234567",
                email="danyal@gmail.com",
                address={"line1": "street 2", "city": "Attock"},
                source_tag="customer_portal",
            )

        self.assertEqual(updated_count, 2)
        self.assertEqual(fake_customers.update_one.await_count, 2)
        second_update = fake_customers.update_one.await_args_list[1].args[1]["$set"]
        self.assertEqual(second_update["name"], "Danyal Khan")
        self.assertEqual(second_update["phone"], "03001234567")
        self.assertEqual(second_update["email"], "danyal@gmail.com")
        self.assertEqual(second_update["status"], "active")
