"""Regression cover for the Phase 1 authentication hardening.

Pins the password policy, the forced-reset gate for accounts that predate it, and
the opaque session token that replaced guessable public-chat conversation ids.
"""

import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.core.password_policy import (
    MIN_PASSWORD_LENGTH,
    describe_password_problem,
    is_password_acceptable,
    validate_password_strength,
)
from app.core.security import PASSWORD_RESET_REQUIRED_DETAIL, get_current_user


class PasswordPolicyTests(unittest.TestCase):
    def test_rejects_the_passwords_these_accounts_actually_used(self):
        for password in ("123456", "1", "password", "Demo@12345", "Admin@12345"):
            with self.subTest(password=password):
                self.assertFalse(is_password_acceptable(password))

    def test_rejects_short_passwords(self):
        self.assertIn(str(MIN_PASSWORD_LENGTH), describe_password_problem("Ab3$xy"))

    def test_rejects_sequences_and_repeats(self):
        self.assertIn("sequence", describe_password_problem("abcdefgh"))
        self.assertIn("repeated", describe_password_problem("aaaaaaaa"))

    def test_requires_three_character_classes(self):
        self.assertIn("three of", describe_password_problem("lowercase123"))
        self.assertIsNone(describe_password_problem("Lowercase123"))

    def test_rejects_passwords_built_from_the_owner_identity(self):
        problem = describe_password_problem("Ahsan!2026x", "ahsanjamil583@gmail.com", "03001234567", "Ahsan Jamil")
        self.assertIn("your name, email, or phone", problem)

    def test_accepts_a_reasonable_password(self):
        self.assertIsNone(describe_password_problem("Str0ng!Pass", "someone@example.com", "03001234567", "Someone Else"))

    def test_validate_raises_422_with_a_readable_message(self):
        with self.assertRaises(HTTPException) as ctx:
            validate_password_strength("password")  # long enough, but on the breach list
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("too common", ctx.exception.detail)

    def test_length_is_checked_before_the_breach_list(self):
        self.assertIn(str(MIN_PASSWORD_LENGTH), describe_password_problem("123456"))


class ForcedResetGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_flagged_account_is_blocked_from_normal_routes(self):
        with self.assertRaises(HTTPException) as ctx:
            await get_current_user({"_id": ObjectId(), "mustResetPassword": True})
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, PASSWORD_RESET_REQUIRED_DETAIL)

    async def test_unflagged_account_passes_through(self):
        user = {"_id": ObjectId(), "mustResetPassword": False}
        self.assertIs(await get_current_user(user), user)

    async def test_account_without_the_field_passes_through(self):
        user = {"_id": ObjectId()}
        self.assertIs(await get_current_user(user), user)


class WeakPasswordFlaggingTests(unittest.IsolatedAsyncioTestCase):
    """A stored bcrypt hash cannot be audited, so login is the only checkpoint."""

    async def _login(self, password):
        from app.services import auth_service

        user = {
            "_id": ObjectId(),
            "email": "legacy@example.com",
            "phone": "03001234567",
            "fullName": "Legacy User",
            "passwordHash": "hash",
            "accountType": "business_owner",
            "globalRole": "user",
            "status": "active",
        }
        db = AsyncMock()
        db.users.find_one = AsyncMock(return_value=user)
        db.users.update_one = AsyncMock()
        with patch.object(auth_service, "get_database", return_value=db), \
             patch.object(auth_service, "verify_password", return_value=True), \
             patch.object(auth_service, "create_access_token", return_value="access"), \
             patch.object(auth_service, "create_refresh_token", return_value="refresh"):
            result = await auth_service.login_user("legacy@example.com", password)
        written = db.users.update_one.await_args.args[1]["$set"]
        return result, written

    async def test_weak_password_flags_the_account_at_login(self):
        result, written = await self._login("123456")
        self.assertTrue(written["mustResetPassword"])
        self.assertTrue(result["user"]["mustResetPassword"])

    async def test_strong_password_clears_the_flag(self):
        result, written = await self._login("Str0ng!Pass")
        self.assertFalse(written["mustResetPassword"])
        self.assertFalse(result["user"]["mustResetPassword"])


class OtpPasswordResetPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_email_reset_rejects_password_containing_full_name_before_consuming_otp(self):
        from app.services import auth_service

        user = {
            "_id": ObjectId(),
            "email": "ahsanjamil583@gmail.com",
            "phone": "",
            "fullName": "Ahsan Jamil",
            "accountType": "business_owner",
            "status": "active",
        }
        db = AsyncMock()
        db.users.find_one = AsyncMock(return_value=user)

        with patch.object(auth_service, "get_database", return_value=db), \
             patch.object(auth_service, "verify_email_otp", AsyncMock()) as verify_email_otp:
            with self.assertRaises(HTTPException) as ctx:
                await auth_service.reset_password_with_email_otp(
                    "ahsanjamil583@gmail.com",
                    "123456",
                    "Ahsan@2026Test",
                    "business_owner",
                )

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("name, email, or phone", ctx.exception.detail)
        verify_email_otp.assert_not_awaited()
        db.users.update_one.assert_not_called()

    async def test_phone_reset_rejects_password_containing_full_name_before_consuming_otp(self):
        from app.services import auth_service

        user = {
            "_id": ObjectId(),
            "email": "customer@example.com",
            "phone": "+923001234567",
            "fullName": "Customer User",
            "accountType": "customer",
            "status": "active",
        }
        db = AsyncMock()
        db.users.find_one = AsyncMock(return_value=user)

        with patch.object(auth_service, "get_database", return_value=db), \
             patch.object(auth_service, "verify_phone_otp", AsyncMock()) as verify_phone_otp:
            with self.assertRaises(HTTPException) as ctx:
                await auth_service.reset_password_with_phone_otp(
                    "03001234567",
                    "123456",
                    "Customer@2026",
                    "customer",
                )

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("name, email, or phone", ctx.exception.detail)
        verify_phone_otp.assert_not_awaited()
        db.users.update_one.assert_not_called()


class PublicChatSessionTokenTests(unittest.IsolatedAsyncioTestCase):
    """Website chat is unauthenticated, so the returned id must not be enumerable."""

    def test_view_exposes_the_token_and_hides_internal_ids(self):
        from app.services.ai_chat_service import public_conversation_view

        view = public_conversation_view(
            {
                "_id": ObjectId(),
                "tenantId": ObjectId(),
                "customerUserId": ObjectId(),
                "publicSessionToken": "opaque-token-value",
                "status": "open",
            }
        )
        self.assertEqual(view["id"], "opaque-token-value")
        self.assertNotIn("tenantId", view)
        self.assertNotIn("customerUserId", view)
        self.assertNotIn("publicSessionToken", view)

    def test_view_id_is_not_an_object_id(self):
        from app.services.ai_chat_service import public_conversation_view

        view = public_conversation_view({"_id": ObjectId(), "publicSessionToken": "opaque-token-value"})
        self.assertFalse(ObjectId.is_valid(view["id"]))

    async def test_lookup_is_scoped_by_token_tenant_and_channel(self):
        from app.services import ai_chat_service

        db = AsyncMock()
        db.conversations.find_one = AsyncMock(return_value=None)
        tenant = {"_id": ObjectId()}
        with patch.object(ai_chat_service, "get_database", return_value=db):
            await ai_chat_service.resolve_public_conversation(tenant, "some-token")
        query = db.conversations.find_one.await_args.args[0]
        self.assertEqual(query["publicSessionToken"], "some-token")
        self.assertEqual(query["tenantId"], tenant["_id"])
        self.assertEqual(query["channel"], "website")

    async def test_blank_token_never_queries(self):
        from app.services import ai_chat_service

        db = AsyncMock()
        with patch.object(ai_chat_service, "get_database", return_value=db):
            self.assertIsNone(await ai_chat_service.resolve_public_conversation({"_id": ObjectId()}, ""))
            self.assertIsNone(await ai_chat_service.resolve_public_conversation({"_id": ObjectId()}, None))
        db.conversations.find_one.assert_not_called()

    async def test_an_object_id_is_not_accepted_as_a_session_token(self):
        """Someone replaying a guessed ObjectId must not resolve a conversation."""
        from app.services import ai_chat_service

        db = AsyncMock()
        db.conversations.find_one = AsyncMock(return_value=None)
        with patch.object(ai_chat_service, "get_database", return_value=db):
            found = await ai_chat_service.resolve_public_conversation({"_id": ObjectId()}, str(ObjectId()))
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
