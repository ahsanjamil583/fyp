import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.services.admin_service import update_admin_user


class AdminServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_admin_user_blocks_self_demotion(self):
        user_id = ObjectId()
        fake_users = type(
            "Users",
            (),
            {
                "find_one": AsyncMock(return_value={"_id": user_id, "globalRole": "platform_admin", "status": "active"}),
                "update_one": AsyncMock(),
            },
        )()
        fake_db = type("FakeDb", (), {"users": fake_users})()
        payload = type("Payload", (), {"status": None, "globalRole": "user", "isEmailVerified": None, "isPhoneVerified": None})()

        with patch("app.services.admin_service.get_database", return_value=fake_db):
            with self.assertRaises(HTTPException) as context:
                await update_admin_user(str(user_id), payload, {"_id": user_id, "globalRole": "platform_admin"})

        self.assertEqual(context.exception.status_code, 409)
        fake_users.update_one.assert_not_awaited()

    async def test_update_admin_user_saves_allowed_changes(self):
        user_id = ObjectId()
        fake_users = type(
            "Users",
            (),
            {
                "find_one": AsyncMock(
                    side_effect=[
                        {"_id": user_id, "fullName": "Owner", "email": "owner@example.com", "phone": "+923001234567", "accountType": "business_owner", "globalRole": "user", "status": "active"},
                        {"_id": user_id, "fullName": "Owner", "email": "owner@example.com", "phone": "+923001234567", "accountType": "business_owner", "globalRole": "platform_admin", "status": "active"},
                    ]
                ),
                "update_one": AsyncMock(),
            },
        )()
        fake_tenants = type("Tenants", (), {"aggregate": lambda self, pipeline: type("Cursor", (), {"to_list": AsyncMock(return_value=[])})()})()
        fake_db = type("FakeDb", (), {"users": fake_users, "tenants": fake_tenants})()
        payload = type("Payload", (), {"status": None, "globalRole": "platform_admin", "isEmailVerified": None, "isPhoneVerified": None})()

        with patch("app.services.admin_service.get_database", return_value=fake_db):
            result = await update_admin_user(str(user_id), payload, {"_id": ObjectId(), "globalRole": "platform_admin"})

        self.assertEqual(result["globalRole"], "platform_admin")
        fake_users.update_one.assert_awaited_once()
