import unittest
from unittest.mock import AsyncMock, call, patch

from bson import ObjectId

from app.services.auth_service import duplicate_account_detail
from app.services.customer_auth_service import register_customer, update_customer_profile


class CustomerAuthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_account_detail_identifies_phone_collision(self):
        detail = duplicate_account_detail(
            {"email": "owner.phase2@example.com", "phone": "03070000001"},
            "adil@gmail.com",
            "03070000001",
        )

        self.assertEqual(detail, "Phone number already exists. Sign in instead.")

    async def test_register_customer_links_existing_guest_customer_records(self):
        user_id = ObjectId()
        fake_users = type("Users", (), {"insert_one": AsyncMock(return_value=type("InsertResult", (), {"inserted_id": user_id})())})()
        fake_profiles = type("Profiles", (), {"insert_one": AsyncMock()})()
        fake_db = type("FakeDb", (), {"users": fake_users, "customer_profiles": fake_profiles})()
        payload = type(
            "Payload",
            (),
            {"fullName": "Danyal Khan", "email": "danyal@gmail.com", "code": "123456", "password": "Str0ng!Secret"},
        )()

        with (
            patch("app.services.customer_auth_service.get_database", return_value=fake_db),
            patch("app.services.customer_auth_service.find_user_by_email_or_phone", AsyncMock(return_value=None)),
            patch("app.services.customer_auth_service.verify_email_otp", AsyncMock(return_value={"verified": True, "consumed": True})) as verify_email_otp,
            patch("app.services.customer_auth_service.hash_password", return_value="hashed"),
            patch("app.services.customer_auth_service.sync_registered_customer_records", AsyncMock()) as sync_mock,
        ):
            session = await register_customer(payload)

        self.assertEqual(session["user"]["fullName"], "Danyal Khan")
        self.assertTrue(session["user"]["isEmailVerified"])
        inserted_user = fake_users.insert_one.await_args.args[0]
        self.assertNotIn("phone", inserted_user)
        # The code is consumed exactly once, and before the account is created. The old
        # order (check without consuming, insert, then consume) left the account behind
        # whenever the consuming check failed, permanently blocking the real owner.
        verify_email_otp.assert_awaited_once_with(
            email="danyal@gmail.com", code="123456", account_type="customer", purpose="register", consume=True
        )
        self.assertLess(
            verify_email_otp.await_args_list.index(verify_email_otp.await_args),
            1,
            "the OTP must be consumed before anything is written",
        )
        self.assertTrue(fake_users.insert_one.await_count, "the account is still created on success")
        sync_mock.assert_awaited_once()
        self.assertEqual(sync_mock.await_args.kwargs["customer_user_id"], user_id)
        self.assertEqual(sync_mock.await_args.kwargs["source_tag"], "customer_portal")

    async def test_update_customer_profile_syncs_linked_customer_records(self):
        user_id = ObjectId()
        fake_users = type("Users", (), {"find_one": AsyncMock(return_value={"_id": user_id, "fullName": "Danyal Khan", "email": "danyal@gmail.com", "phone": "03001234567"})})()
        fake_profiles = type("Profiles", (), {"update_one": AsyncMock()})()
        fake_db = type("FakeDb", (), {"users": fake_users, "customer_profiles": fake_profiles})()
        payload = type(
            "Payload",
            (),
            {
                "phone": "03007654321",
                "defaultAddress": {"line1": "street 2", "city": "Attock"},
                "savedAddresses": [],
                "preferences": {},
            },
        )()

        with (
            patch("app.services.customer_auth_service.get_database", return_value=fake_db),
            patch("app.services.customer_auth_service.sync_registered_customer_records", AsyncMock()) as sync_mock,
            patch(
                "app.services.customer_auth_service.get_customer_profile",
                AsyncMock(return_value={"id": "profile-1", "userId": str(user_id), "phone": "03007654321", "defaultAddress": {"line1": "street 2", "city": "Attock"}}),
            ),
        ):
            result = await update_customer_profile(str(user_id), payload)

        self.assertEqual(result["phone"], "03007654321")
        sync_mock.assert_awaited_once()
        self.assertEqual(sync_mock.await_args.kwargs["address"], {"line1": "street 2", "city": "Attock"})
