import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.services.customer_service import (
    ensure_customer_record_for_tenant,
    find_or_create_customer_from_transaction,
    sync_registered_customer_records,
)


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
        # `status` is the business's call, not the customer's. Writing it here let a
        # customer clear an inactive or blocked flag just by saving their own profile.
        self.assertNotIn("status", second_update)


class GuestRecordClaimingTests(unittest.IsolatedAsyncioTestCase):
    """Guest records are matched by phone or email across every tenant.

    That is what makes registration link up a customer's past walk-in orders, and also
    what made it possible to claim somebody else's record by typing their phone number.
    A record the business has switched off must not be claimable at all.
    """

    def _db(self, records):
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

        customers = type(
            "Customers",
            (),
            {"find": lambda self, query: AsyncCursor(records), "update_one": AsyncMock()},
        )()
        return type("FakeDb", (), {"customers": customers})(), customers

    async def _sync(self, records, user_id):
        fake_db, customers = self._db(records)
        with patch("app.services.customer_service.get_database", return_value=fake_db):
            count = await sync_registered_customer_records(
                customer_user_id=user_id, name="Danyal Khan", phone="03001234567", email="danyal@gmail.com"
            )
        return count, customers

    async def test_a_blocked_record_belonging_to_someone_else_is_not_claimed(self):
        count, customers = await self._sync(
            [{"_id": ObjectId(), "customerUserId": None, "status": "blocked", "phone": "03001234567", "tags": []}],
            ObjectId(),
        )
        self.assertEqual(count, 0)
        customers.update_one.assert_not_awaited()

    async def test_an_inactive_record_belonging_to_someone_else_is_not_claimed(self):
        count, customers = await self._sync(
            [{"_id": ObjectId(), "customerUserId": None, "status": "inactive", "phone": "03001234567", "tags": []}],
            ObjectId(),
        )
        self.assertEqual(count, 0)

    async def test_an_ordinary_guest_record_is_still_linked(self):
        """The feature must keep working: this is how past walk-in orders join up."""
        count, customers = await self._sync(
            [{"_id": ObjectId(), "customerUserId": None, "status": "active", "phone": "03001234567", "tags": []}],
            ObjectId(),
        )
        self.assertEqual(count, 1)
        self.assertIn("customerUserId", customers.update_one.await_args.args[1]["$set"])

    async def test_status_is_never_written(self):
        user_id = ObjectId()
        _, customers = await self._sync(
            [{"_id": ObjectId(), "customerUserId": user_id, "status": "blocked", "phone": "03001234567", "tags": []}],
            user_id,
        )
        self.assertNotIn("status", customers.update_one.await_args.args[1]["$set"])


class ClaimingRequiresVerifiedContactDetailsTests(unittest.IsolatedAsyncioTestCase):
    """Matching a guest record by email or phone CLAIMS it, across every tenant.

    Doing that on a detail the account has merely typed in let anyone take over a
    stranger's order history by entering their phone number. The earlier fixture ignored
    the query entirely, so it could not see which clauses were built; this one captures
    the query itself.
    """

    async def _captured_query(self, **kwargs):
        from unittest.mock import AsyncMock, MagicMock, patch

        captured = {}

        class AsyncCursor:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        def find(query):
            captured["query"] = query
            return AsyncCursor()

        customers = MagicMock()
        customers.find = find
        customers.update_one = AsyncMock()
        fake_db = type("FakeDb", (), {"customers": customers})()
        with patch("app.services.customer_service.get_database", return_value=fake_db):
            await sync_registered_customer_records(
                customer_user_id=ObjectId(),
                name="Danyal Khan",
                phone="03001234567",
                email="danyal@gmail.com",
                **kwargs,
            )
        return captured["query"]["$or"]

    async def test_unverified_details_do_not_claim_anything(self):
        clauses = await self._captured_query()
        self.assertEqual(len(clauses), 1, f"only the already-linked clause should remain: {clauses}")
        self.assertIn("customerUserId", clauses[0])

    async def test_a_verified_email_may_claim(self):
        clauses = await self._captured_query(email_verified=True)
        self.assertIn({"email": "danyal@gmail.com"}, clauses)
        self.assertNotIn({"phone": "03001234567"}, clauses)

    async def test_a_verified_phone_may_claim(self):
        clauses = await self._captured_query(phone_verified=True)
        self.assertIn({"phone": "03001234567"}, clauses)

    async def test_registration_claims_by_the_otp_verified_email(self):
        """The registration OTP proves the email, which is what makes guest order
        history join up. The phone is only typed in, so it must not claim."""
        import inspect

        from app.services import customer_auth_service

        source = inspect.getsource(customer_auth_service.register_customer)
        self.assertIn("email_verified=True", source)
        self.assertIn('phone_verified=bool(user.get("isPhoneVerified"))', source)


class SharedClaimingFunctionTests(unittest.IsolatedAsyncioTestCase):
    """`sync_registered_customer_records` was given a verification gate two rounds ago.
    `find_or_create_customer_from_transaction`, which every cart, favourite and checkout
    call reaches, was the twin that was missed."""

    async def _captured_query(self, **kwargs):
        from unittest.mock import AsyncMock, MagicMock, patch

        captured = {}

        def find_one(query):
            captured.setdefault("query", query)
            return AsyncMock(return_value=None)()

        customers = MagicMock()
        customers.find_one = find_one
        customers.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
        fake_db = type("FakeDb", (), {"customers": customers})()
        with patch("app.services.customer_service.get_database", return_value=fake_db), patch(
            "app.core.module_guard.ensure_tenant_module_usage_available", AsyncMock()
        ):
            await find_or_create_customer_from_transaction(
                {"_id": ObjectId()},
                customer_user_id=ObjectId(),
                name="Danyal",
                phone="03001234567",
                email="danyal@gmail.com",
                **kwargs,
            )
        return captured["query"]["$or"]

    async def test_unverified_details_cannot_claim(self):
        clauses = await self._captured_query()
        self.assertEqual(len(clauses), 1, f"only the linked-account clause should remain: {clauses}")
        self.assertIn("customerUserId", clauses[0])

    async def test_a_verified_email_may_claim(self):
        clauses = await self._captured_query(email_verified=True)
        self.assertIn({"email": "danyal@gmail.com"}, clauses)

    async def test_a_verified_phone_may_claim(self):
        clauses = await self._captured_query(phone_verified=True)
        self.assertIn({"phone": "03001234567"}, clauses)

    async def test_the_customer_cap_is_consulted_on_this_path_too(self):
        """Guarding only manual creation meant orders walked straight past the cap."""
        import inspect

        from app.services import customer_service

        source = inspect.getsource(customer_service.find_or_create_customer_from_transaction)
        self.assertIn("ensure_tenant_module_usage_available", source)
