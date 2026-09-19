import unittest
from datetime import datetime, timezone

from bson import ObjectId

from fastapi import HTTPException

from app.services.otp_service import (
    as_aware_utc,
    build_failed_attempt_update,
    hash_otp_code,
    mask_phone,
    normalize_account_type,
    normalize_otp_code,
    normalize_otp_purpose,
    verify_otp_hash,
)


class Phase29PhoneOtpTests(unittest.TestCase):
    def test_normalize_otp_code_keeps_digits_only(self):
        self.assertEqual(normalize_otp_code(" 12-34 56 "), "123456")

    def test_mask_phone_keeps_safe_preview_only(self):
        self.assertEqual(mask_phone("03001234567"), "0300****567")

    def test_hash_round_trip_uses_phone_purpose_and_account_type(self):
        digest = hash_otp_code("03001234567", "123456", "login", "customer")
        self.assertTrue(verify_otp_hash("03001234567", "123456", "login", "customer", digest))
        self.assertFalse(verify_otp_hash("03001234567", "123456", "register", "customer", digest))
        self.assertFalse(verify_otp_hash("03001234567", "000000", "login", "customer", digest))

    def test_naive_mongo_datetime_is_normalized_to_utc(self):
        naive = datetime(2026, 7, 2, 12, 0, 0)
        normalized = as_aware_utc(naive)
        self.assertEqual(normalized.tzinfo, timezone.utc)
        self.assertLess(normalized, datetime(2026, 7, 2, 12, 1, 0, tzinfo=timezone.utc))

    def test_invalid_account_type_and_purpose_are_rejected(self):
        with self.assertRaises(HTTPException):
            normalize_account_type("admin")
        with self.assertRaises(HTTPException):
            normalize_otp_purpose("magic")

    def test_failed_attempt_update_locks_on_final_attempt(self):
        now = datetime.now(timezone.utc)
        update, remaining, locked = build_failed_attempt_update({"attempts": 4, "maxAttempts": 5}, now)
        self.assertEqual(update["attempts"], 5)
        self.assertEqual(update["status"], "locked")
        self.assertEqual(remaining, 0)
        self.assertTrue(locked)

    def test_failed_attempt_update_keeps_pending_before_limit(self):
        now = datetime.now(timezone.utc)
        update, remaining, locked = build_failed_attempt_update({"attempts": 1, "maxAttempts": 5}, now)
        self.assertEqual(update["attempts"], 2)
        self.assertNotIn("status", update)
        self.assertEqual(remaining, 3)
        self.assertFalse(locked)


class VerifyPhoneReachabilityTests(unittest.IsolatedAsyncioTestCase):
    """Adding a phone number to an account that has none is the whole point of
    verify_phone, so requiring the number to already be on a user made the flow
    impossible to reach: a customer never gets users.phone until this succeeds."""

    async def _validate(self, *, existing_user, for_user_id):
        from unittest.mock import AsyncMock, patch

        from app.services import otp_service

        with patch.object(otp_service, "_find_user_by_phone", AsyncMock(return_value=existing_user)):
            await otp_service._validate_purpose_against_user("03001234567", "customer", "verify_phone", for_user_id)

    async def test_an_authenticated_user_can_verify_a_number_they_do_not_have_yet(self):
        await self._validate(existing_user=None, for_user_id=ObjectId())

    async def test_re_verifying_your_own_number_is_allowed(self):
        user_id = ObjectId()
        await self._validate(existing_user={"_id": user_id, "status": "active"}, for_user_id=user_id)

    async def test_a_number_owned_by_someone_else_is_refused(self):
        with self.assertRaises(HTTPException) as caught:
            await self._validate(existing_user={"_id": ObjectId(), "status": "active"}, for_user_id=ObjectId())
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("another account", caught.exception.detail)

    async def test_without_an_authenticated_user_the_old_rule_still_applies(self):
        """Unauthenticated purposes such as login and password reset must still require
        an existing account."""
        with self.assertRaises(HTTPException) as caught:
            await self._validate(existing_user=None, for_user_id=None)
        self.assertEqual(caught.exception.status_code, 404)
