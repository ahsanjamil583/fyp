import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.services.admin_service import decide_admin_website_request, update_admin_user


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

    async def test_decide_admin_website_request_approves_and_publishes(self):
        tenant_id = ObjectId()
        admin_id = ObjectId()
        tenant = {"_id": tenant_id, "name": "Ready Business", "settings": {"publicVisibility": False}}
        criteria = {"isComplete": True, "checks": [], "missing": [], "score": 8, "total": 8}
        fake_tenants = type(
            "Tenants",
            (),
            {
                "find_one": AsyncMock(return_value=tenant),
                "update_one": AsyncMock(),
            },
        )()
        fake_audit_logs = type("AuditLogs", (), {"insert_one": AsyncMock()})()
        fake_db = type("FakeDb", (), {"tenants": fake_tenants, "audit_logs": fake_audit_logs})()
        payload = type("Payload", (), {"status": "approved", "note": "Looks complete."})()
        refreshed = {"id": str(tenant_id), "name": "Ready Business", "websiteStatus": "published"}

        with patch("app.services.admin_service.get_database", return_value=fake_db), \
             patch("app.services.admin_service.build_business_formation_criteria", AsyncMock(return_value=criteria)), \
             patch("app.services.admin_service.list_admin_tenants", AsyncMock(return_value=[refreshed])):
            result = await decide_admin_website_request(str(tenant_id), payload, {"_id": admin_id})

        update_doc = fake_tenants.update_one.await_args.args[1]["$set"]
        self.assertEqual(result["websiteStatus"], "published")
        self.assertEqual(update_doc["status"], "active")
        self.assertEqual(update_doc["websiteStatus"], "published")
        self.assertEqual(update_doc["settings"]["publicVisibility"], True)
        self.assertEqual(update_doc["websiteApprovalStatus"], "approved")
        fake_audit_logs.insert_one.assert_awaited_once()

    async def test_decide_admin_website_request_blocks_incomplete_approval(self):
        tenant_id = ObjectId()
        tenant = {"_id": tenant_id, "name": "Incomplete Business", "settings": {}}
        criteria = {
            "isComplete": False,
            "checks": [],
            "missing": [{"label": "Sellable or bookable item"}],
            "score": 7,
            "total": 8,
        }
        fake_tenants = type(
            "Tenants",
            (),
            {
                "find_one": AsyncMock(return_value=tenant),
                "update_one": AsyncMock(),
            },
        )()
        fake_db = type("FakeDb", (), {"tenants": fake_tenants})()
        payload = type("Payload", (), {"status": "approved", "note": ""})()

        with patch("app.services.admin_service.get_database", return_value=fake_db), \
             patch("app.services.admin_service.build_business_formation_criteria", AsyncMock(return_value=criteria)):
            with self.assertRaises(HTTPException) as context:
                await decide_admin_website_request(str(tenant_id), payload, {"_id": ObjectId()})

        self.assertEqual(context.exception.status_code, 409)
        fake_tenants.update_one.assert_not_awaited()
