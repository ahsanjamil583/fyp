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


class ModuleUsageLimitTests(unittest.IsolatedAsyncioTestCase):
    """Plan usage caps were a `return None` stub while five call sites awaited it as a
    guard, so every limit in the product was silently unenforced."""

    MODULE = {
        "code": "items",
        "isActive": True,
        "usageLimits": {
            "starter": {"metricCode": "active_items", "label": "Active items", "limit": 50},
            "scale": {"metricCode": "active_items", "label": "Active items", "limit": None},
        },
    }

    def _db(self, *, module, tenant, used):
        from unittest.mock import AsyncMock, MagicMock

        collection = MagicMock()
        collection.count_documents = AsyncMock(return_value=used)
        db = MagicMock()
        db.modules.find_one = AsyncMock(return_value=module)
        db.tenants.find_one = AsyncMock(return_value=tenant)
        db.__getitem__ = MagicMock(return_value=collection)
        return db

    async def _check(self, *, module=None, plan="starter", used=0, increment=1):
        from unittest.mock import patch

        from app.core import module_guard

        db = self._db(module=self.MODULE if module is None else module, tenant={"planCode": plan}, used=used)
        with patch.object(module_guard, "get_database", return_value=db):
            await module_guard.ensure_tenant_module_usage_available(ObjectId(), "items", increment)

    async def test_usage_below_the_limit_is_allowed(self):
        await self._check(used=49)

    async def test_the_limit_is_enforced_once_it_would_be_exceeded(self):
        with self.assertRaises(HTTPException) as caught:
            await self._check(used=50)
        self.assertEqual(caught.exception.status_code, 402)
        self.assertIn("Active items", caught.exception.detail)

    async def test_a_null_limit_means_unlimited(self):
        await self._check(plan="scale", used=10_000)

    async def test_an_unknown_plan_is_not_treated_as_zero(self):
        """Failing closed on a missing plan entry would lock out a legitimate tenant."""
        await self._check(plan="enterprise", used=10_000)

    async def test_an_unmapped_metric_fails_open(self):
        module = {**self.MODULE, "usageLimits": {"starter": {"metricCode": "moon_phases", "limit": 1}}}
        await self._check(module=module, used=500)

    async def test_a_disabled_module_imposes_no_limit(self):
        from unittest.mock import patch

        from app.core import module_guard

        db = self._db(module=None, tenant={"planCode": "starter"}, used=10_000)
        with patch.object(module_guard, "get_database", return_value=db):
            await module_guard.ensure_tenant_module_usage_available(ObjectId(), "items", 1)
