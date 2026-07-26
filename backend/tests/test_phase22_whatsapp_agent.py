import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi.testclient import TestClient

from app.services.whatsapp_service import process_whatsapp_webhook_payload, verify_whatsapp_webhook


class Phase22WhatsAppAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_verify_whatsapp_webhook_accepts_global_token(self):
        result = await verify_whatsapp_webhook("subscribe", "bizxus-whatsapp-verify", "12345")
        self.assertEqual(result, "12345")

    async def test_verify_whatsapp_webhook_accepts_tenant_token(self):
        fake_db = type(
            "FakeDb",
            (),
            {"whatsapp_integrations": type("Integrations", (), {"find_one": AsyncMock(return_value={"_id": ObjectId(), "isConnected": True})})()},
        )()

        with patch("app.services.whatsapp_service.get_database", return_value=fake_db):
            result = await verify_whatsapp_webhook("subscribe", "tenant-token", "abc")

        self.assertEqual(result, "abc")

    async def test_process_whatsapp_webhook_payload_uses_inbound_pipeline(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "pn-1", "display_phone_number": "+923001234567"},
                                "contacts": [{"wa_id": "923001112223", "profile": {"name": "Ali"}}],
                                "messages": [{"id": "msg-1", "from": "923001112223", "type": "text", "text": {"body": "2 burgers order kar do"}}],
                            }
                        }
                    ]
                }
            ]
        }
        tenant = {"_id": ObjectId(), "name": "Demo Biz", "enabledModuleCodes": ["ai_chat", "whatsapp_agent"]}
        integration = {"_id": ObjectId(), "provider": "mock", "isConnected": True}
        inbound_result = {
            "tenant": {"id": str(tenant["_id"])},
            "conversation": {"id": str(ObjectId())},
            "reply": "Sure",
        }

        with (
            patch("app.services.whatsapp_service.find_whatsapp_integration_for_inbound", AsyncMock(return_value=(integration, tenant))),
            patch("app.services.whatsapp_service.process_whatsapp_inbound", AsyncMock(return_value=inbound_result)),
        ):
            result = await process_whatsapp_webhook_payload(payload)

        self.assertEqual(result["processedCount"], 1)
        self.assertEqual(result["items"][0]["reply"], "Sure")

    async def test_process_whatsapp_webhook_payload_rejects_invalid_body(self):
        with self.assertRaisesRegex(Exception, "Invalid WhatsApp webhook payload"):
            await process_whatsapp_webhook_payload(["not-a-dict"])  # type: ignore[arg-type]

    def test_whatsapp_webhook_receive_rejects_invalid_json(self):
        with (
            patch("app.main.connect_to_mongo", new=AsyncMock()),
            patch("app.main.close_mongo_connection", new=AsyncMock()),
            patch("app.main.create_indexes", new=AsyncMock()),
            patch("app.main.seed_default_admin", new=AsyncMock()),
            patch("app.main.seed_modules", new=AsyncMock()),
            patch("app.main.seed_business_categories", new=AsyncMock()),
        ):
            from app.main import create_app

            app = create_app()
            with TestClient(app) as client:
                response = client.post("/api/v1/webhooks/whatsapp", data="{broken json", headers={"Content-Type": "application/json"})

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
