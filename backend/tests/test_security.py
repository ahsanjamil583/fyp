import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


class SecurityTests(unittest.TestCase):
    def test_password_hash_round_trip(self):
        password_hash = hash_password("Test1234!")
        self.assertTrue(verify_password("Test1234!", password_hash))
        self.assertFalse(verify_password("WrongPassword", password_hash))

    def test_access_and_refresh_tokens_decode(self):
        user = {"_id": ObjectId(), "accountType": "business_owner", "globalRole": "user"}
        access = create_access_token(user)
        refresh = create_refresh_token(user)

        access_payload = decode_token(access, expected_type="access")
        refresh_payload = decode_token(refresh, expected_type="refresh")

        self.assertEqual(access_payload["sub"], str(user["_id"]))
        self.assertEqual(access_payload["accountType"], "business_owner")
        self.assertEqual(refresh_payload["sub"], str(user["_id"]))

    def test_decode_token_rejects_wrong_type(self):
        token = create_token("abc123", "refresh", timedelta(minutes=5))
        with self.assertRaises(HTTPException) as context:
            decode_token(token, expected_type="access")
        self.assertEqual(context.exception.status_code, 401)

    def test_get_current_business_user_rejects_customer(self):
        from app.core.security import get_current_business_user

        async def runner():
            with self.assertRaises(HTTPException) as context:
                await get_current_business_user({"accountType": "customer"})
            self.assertEqual(context.exception.status_code, 403)

        import asyncio

        asyncio.run(runner())

    def test_get_current_user_loads_active_user(self):
        from fastapi.security import HTTPAuthorizationCredentials
        from app.core.security import get_current_user

        user = {
            "_id": ObjectId(),
            "accountType": "business_owner",
            "globalRole": "user",
            "status": "active",
        }
        access = create_access_token(user)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access)
        fake_db = type("FakeDb", (), {"users": type("Users", (), {"find_one": AsyncMock(return_value=user)})()})()

        async def runner():
            with patch("app.core.security.get_database", return_value=fake_db):
                current = await get_current_user(credentials)
            self.assertEqual(current["_id"], user["_id"])

        import asyncio

        asyncio.run(runner())
