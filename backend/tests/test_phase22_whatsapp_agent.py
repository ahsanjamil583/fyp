"""WhatsApp agent tests.

This file previously covered the Meta Cloud API webhook, which was retired when the
project moved to the Baileys linked-device bridge. It now covers the surface that
actually exists: the bridge endpoints and their token authentication.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services import whatsapp_service
from app.services.whatsapp_service import (
    build_bridge_pairing_url,
    list_bridge_tenants,
    build_whatsapp_deep_link,
    normalize_phone,
    process_bridge_inbound,
    process_bridge_status,
)


class PhoneNormalizationTests(unittest.TestCase):
    """WhatsApp numbers are stored in E.164 so lookups match across tenants."""

    def test_local_pakistani_number_becomes_e164(self):
        self.assertEqual(normalize_phone("03345625097"), "+923345625097")

    def test_already_normalized_number_is_unchanged(self):
        self.assertEqual(normalize_phone("+923345625097"), "+923345625097")

    def test_international_number_is_kept_international(self):
        self.assertEqual(normalize_phone("+1 555-627-7647"), "+15556277647")

    def test_double_zero_prefix_becomes_plus(self):
        self.assertEqual(normalize_phone("00923345625097"), "+923345625097")

    def test_blank_stays_blank(self):
        self.assertEqual(normalize_phone(""), "")
        self.assertEqual(normalize_phone(None), "")

    def test_deep_link_uses_digits_only(self):
        self.assertEqual(build_whatsapp_deep_link("+92 334 5625097"), "https://wa.me/923345625097")

    def test_deep_link_is_empty_without_a_number(self):
        self.assertEqual(build_whatsapp_deep_link(""), "")


class BridgeAuthTests(unittest.IsolatedAsyncioTestCase):
    """The bridge token is the only credential on these endpoints."""

    def _payload(self):
        return type(
            "Payload",
            (),
            {
                "tenantId": str(ObjectId()),
                "status": "ready",
                "connectedNumber": "923345625097",
                "lastError": "",
                "customerPhone": "923001112223",
                "customerName": "Ali",
                "messageText": "do you have shoes?",
                "providerMessageId": "msg-1",
                "rawPayload": {},
            },
        )()

    async def test_status_rejects_an_unknown_token(self):
        from app.services import whatsapp_service

        db = AsyncMock()
        db.whatsapp_integrations.find_one = AsyncMock(return_value=None)
        with patch.object(whatsapp_service, "get_database", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                await process_bridge_status(self._payload(), "wrong-token")
        self.assertEqual(ctx.exception.status_code, 401)

    async def test_inbound_rejects_an_unknown_token(self):
        from app.services import whatsapp_service

        db = AsyncMock()
        db.whatsapp_integrations.find_one = AsyncMock(return_value=None)
        with patch.object(whatsapp_service, "get_database", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                await process_bridge_inbound(self._payload(), "wrong-token")
        self.assertEqual(ctx.exception.status_code, 401)

    async def test_inbound_lookup_is_scoped_to_tenant_token_and_provider(self):
        from app.services import whatsapp_service

        db = AsyncMock()
        db.whatsapp_integrations.find_one = AsyncMock(return_value=None)
        payload = self._payload()
        with patch.object(whatsapp_service, "get_database", return_value=db):
            with self.assertRaises(HTTPException):
                await process_bridge_inbound(payload, "some-token")
        query = db.whatsapp_integrations.find_one.await_args.args[0]
        self.assertEqual(query["bridgeToken"], "some-token")
        self.assertEqual(query["provider"], "baileys")
        self.assertTrue(query["isConnected"])

    async def test_inbound_is_refused_when_the_agent_is_disabled(self):
        from app.services import whatsapp_service

        db = AsyncMock()
        db.whatsapp_integrations.find_one = AsyncMock(
            return_value={"_id": ObjectId(), "agentEnabled": False, "provider": "baileys"}
        )
        with patch.object(whatsapp_service, "get_database", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                await process_bridge_inbound(self._payload(), "good-token")
        self.assertEqual(ctx.exception.status_code, 403)


class BridgePairingUrlTests(unittest.TestCase):
    """The owner-facing link that opens their QR page on the bridge."""

    def test_link_targets_the_tenants_own_pairing_page(self):
        with patch.object(whatsapp_service.settings, "whatsapp_bridge_public_url", "http://localhost:3005"):
            self.assertEqual(
                build_bridge_pairing_url("6a4f571923bff861a6f43e36"),
                "http://localhost:3005/pair/6a4f571923bff861a6f43e36",
            )

    def test_configured_base_url_is_used_without_a_double_slash(self):
        with patch.object(whatsapp_service.settings, "whatsapp_bridge_public_url", "https://bridge.example.com/"):
            self.assertEqual(build_bridge_pairing_url("abc"), "https://bridge.example.com/pair/abc")

    def test_missing_base_url_falls_back_to_the_local_bridge(self):
        with patch.object(whatsapp_service.settings, "whatsapp_bridge_public_url", ""):
            self.assertEqual(build_bridge_pairing_url("abc"), "http://localhost:3005/pair/abc")

    def test_owner_settings_expose_the_pairing_link(self):
        data = whatsapp_service._serialize_owner_whatsapp_settings(None, {"_id": ObjectId("6a4f571923bff861a6f43e36")})
        self.assertTrue(data["bridgePairingUrl"].endswith("/pair/6a4f571923bff861a6f43e36"))


class _Cursor:
    """Minimal async cursor stand-in for motor's find()."""

    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        async def gen():
            for doc in self._docs:
                yield doc

        return gen()


class BridgeTenantDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    """The bridge asks the API which businesses it should connect."""

    def _db(self, integrations, tenant=None, module_enabled=True):
        db = MagicMock()
        db.whatsapp_integrations.find = MagicMock(return_value=_Cursor(integrations))
        db.tenants.find_one = AsyncMock(return_value=tenant)
        db.tenant_modules.find_one = AsyncMock(return_value={"status": "enabled"} if module_enabled else None)
        return db

    async def test_discovery_is_disabled_until_a_key_is_configured(self):
        with patch.object(whatsapp_service.settings, "whatsapp_bridge_admin_key", ""):
            with self.assertRaises(HTTPException) as ctx:
                await list_bridge_tenants("anything")
        self.assertEqual(ctx.exception.status_code, 503)

    async def test_a_wrong_key_is_rejected(self):
        with patch.object(whatsapp_service.settings, "whatsapp_bridge_admin_key", "right-key"):
            with self.assertRaises(HTTPException) as ctx:
                await list_bridge_tenants("wrong-key")
        self.assertEqual(ctx.exception.status_code, 401)

    async def test_a_connected_business_is_returned_with_its_token(self):
        tenant_oid = ObjectId()
        db = self._db(
            [{"tenantId": tenant_oid, "bridgeToken": "tok-1", "displayName": "Style"}],
            tenant={"_id": tenant_oid, "name": "Style"},
        )
        with (
            patch.object(whatsapp_service.settings, "whatsapp_bridge_admin_key", "right-key"),
            patch.object(whatsapp_service, "get_database", return_value=db),
        ):
            data = await list_bridge_tenants("right-key")
        self.assertEqual(data["tenants"], [{"tenantId": str(tenant_oid), "bridgeToken": "tok-1", "label": "Style"}])
        # Only saved Baileys integrations that still hold a token are offered.
        query = db.whatsapp_integrations.find.call_args[0][0]
        self.assertEqual(query["provider"], "baileys")
        self.assertTrue(query["isConnected"])

    async def test_a_business_without_the_approved_module_is_skipped(self):
        tenant_oid = ObjectId()
        db = self._db(
            [{"tenantId": tenant_oid, "bridgeToken": "tok-1", "displayName": "Style"}],
            tenant={"_id": tenant_oid, "name": "Style"},
            module_enabled=False,
        )
        with (
            patch.object(whatsapp_service.settings, "whatsapp_bridge_admin_key", "right-key"),
            patch.object(whatsapp_service, "get_database", return_value=db),
        ):
            data = await list_bridge_tenants("right-key")
        self.assertEqual(data["tenants"], [])

    async def test_a_missing_or_suspended_tenant_is_skipped(self):
        db = self._db([{"tenantId": ObjectId(), "bridgeToken": "tok-1"}], tenant=None)
        with (
            patch.object(whatsapp_service.settings, "whatsapp_bridge_admin_key", "right-key"),
            patch.object(whatsapp_service, "get_database", return_value=db),
        ):
            data = await list_bridge_tenants("right-key")
        self.assertEqual(data["tenants"], [])


class RetiredWebhookTests(unittest.TestCase):
    def test_the_meta_webhook_route_is_gone(self):
        with (
            patch("app.main.connect_to_mongo", new=AsyncMock()),
            patch("app.main.close_mongo_connection", new=AsyncMock()),
            patch("app.main.create_indexes", new=AsyncMock()),
            patch("app.main.seed_default_admin", new=AsyncMock()),
            patch("app.main.seed_modules", new=AsyncMock()),
            patch("app.main.seed_business_categories", new=AsyncMock()),
        ):
            from app.main import create_app

            with TestClient(create_app()) as client:
                self.assertEqual(client.post("/api/v1/webhooks/whatsapp", json={}).status_code, 404)
                self.assertEqual(client.get("/api/v1/webhooks/whatsapp").status_code, 404)


if __name__ == "__main__":
    unittest.main()
