import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.core.permissions import get_owned_tenant_or_403, require_platform_admin


class PermissionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_can_access_owned_tenant(self):
        tenant_id = ObjectId()
        owner_id = ObjectId()
        tenant = {"_id": tenant_id, "ownerUserId": owner_id}
        fake_db = type("FakeDb", (), {"tenants": type("Tenants", (), {"find_one": AsyncMock(return_value=tenant)})()})()

        with patch("app.core.permissions.get_database", return_value=fake_db):
            result = await get_owned_tenant_or_403(tenant_id, {"_id": owner_id, "globalRole": "user"})

        self.assertEqual(result["_id"], tenant_id)
        fake_db.tenants.find_one.assert_awaited_once_with({"_id": tenant_id, "ownerUserId": owner_id})

    async def test_platform_admin_bypasses_owner_filter(self):
        tenant_id = ObjectId()
        tenant = {"_id": tenant_id, "ownerUserId": ObjectId()}
        fake_db = type("FakeDb", (), {"tenants": type("Tenants", (), {"find_one": AsyncMock(return_value=tenant)})()})()

        with patch("app.core.permissions.get_database", return_value=fake_db):
            result = await get_owned_tenant_or_403(tenant_id, {"_id": ObjectId(), "globalRole": "platform_admin"})

        self.assertEqual(result["_id"], tenant_id)
        fake_db.tenants.find_one.assert_awaited_once_with({"_id": tenant_id})

    async def test_missing_tenant_raises_404(self):
        fake_db = type("FakeDb", (), {"tenants": type("Tenants", (), {"find_one": AsyncMock(return_value=None)})()})()
        with patch("app.core.permissions.get_database", return_value=fake_db):
            with self.assertRaises(HTTPException) as context:
                await get_owned_tenant_or_403(ObjectId(), {"_id": ObjectId(), "globalRole": "user"})
        self.assertEqual(context.exception.status_code, 404)

    def test_require_platform_admin_rejects_regular_user(self):
        with self.assertRaises(HTTPException) as context:
            require_platform_admin({"globalRole": "user"})
        self.assertEqual(context.exception.status_code, 403)
