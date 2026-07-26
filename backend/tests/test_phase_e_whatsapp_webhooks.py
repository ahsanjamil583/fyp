import unittest
from unittest.mock import patch

import httpx

from app.services.whatsapp_service import _post_meta_waba_webhook_subscription


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"success": True}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://graph.facebook.com/test")
            response = httpx.Response(self.status_code, request=request, json=self._payload)
            raise httpx.HTTPStatusError("error", request=request, response=response)


class FakeAsyncClient:
    calls = []
    responses = []

    def __init__(self, timeout=25):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, endpoint, params=None, json=None):
        self.__class__.calls.append({"endpoint": endpoint, "params": params or {}, "json": json})
        if self.__class__.responses:
            return self.__class__.responses.pop(0)
        return FakeResponse()


class PhaseEWhatsAppWebhookSubscriptionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        FakeAsyncClient.calls = []
        FakeAsyncClient.responses = []

    async def test_subscribe_waba_webhooks_posts_callback_and_verify_token(self):
        FakeAsyncClient.responses = [FakeResponse(200, {"success": True})]
        with patch("app.services.whatsapp_service.httpx.AsyncClient", FakeAsyncClient):
            result = await _post_meta_waba_webhook_subscription(
                waba_id="12345",
                access_token="token",
                api_version="v21.0",
                callback_url="https://example.ngrok-free.app/api/v1/webhooks/whatsapp",
                verify_token="verify-token",
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(FakeAsyncClient.calls), 1)
        call = FakeAsyncClient.calls[0]
        self.assertIn("/v21.0/12345/subscribed_apps", call["endpoint"])
        self.assertEqual(call["params"], {"access_token": "token"})
        self.assertEqual(call["json"]["override_callback_uri"], "https://example.ngrok-free.app/api/v1/webhooks/whatsapp")
        self.assertEqual(call["json"]["verify_token"], "verify-token")

    async def test_subscribe_waba_webhooks_falls_back_to_plain_post(self):
        FakeAsyncClient.responses = [
            FakeResponse(400, {"error": {"message": "Unsupported post param"}}),
            FakeResponse(200, {"success": True}),
        ]
        with patch("app.services.whatsapp_service.httpx.AsyncClient", FakeAsyncClient):
            result = await _post_meta_waba_webhook_subscription(
                waba_id="waba-1",
                access_token="token",
                api_version="v23.0",
                callback_url="https://example.com/api/v1/webhooks/whatsapp",
                verify_token="verify",
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(FakeAsyncClient.calls), 2)
        self.assertIsNotNone(FakeAsyncClient.calls[0]["json"])
        self.assertIsNone(FakeAsyncClient.calls[1]["json"])


if __name__ == "__main__":
    unittest.main()
