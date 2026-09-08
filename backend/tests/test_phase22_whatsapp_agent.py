"""WhatsApp agent tests.

This file previously covered the Meta Cloud API webhook, which was retired when the
project moved to the Baileys linked-device bridge. It now covers the surface that
actually exists: the bridge endpoints and their token authentication.
"""

import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.whatsapp_service import (
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
