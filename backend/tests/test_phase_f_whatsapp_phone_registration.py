import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from app.services.whatsapp_service import _post_meta_phone_number_registration


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


class PhaseFWhatsAppPhoneRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        FakeAsyncClient.calls = []
        FakeAsyncClient.responses = []

    async def test_register_phone_posts_to_meta_register_endpoint(self):
        FakeAsyncClient.responses = [FakeResponse(200, {"success": True})]
        with patch("app.services.whatsapp_service.httpx.AsyncClient", FakeAsyncClient):
            result = await _post_meta_phone_number_registration(
                phone_number_id="987654321",
                access_token="business-token",
                api_version="v21.0",
                pin="123456",
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(FakeAsyncClient.calls), 1)
        call = FakeAsyncClient.calls[0]
        self.assertIn("/v21.0/987654321/register", call["endpoint"])
        self.assertEqual(call["params"], {"access_token": "business-token"})
        self.assertEqual(call["json"], {"messaging_product": "whatsapp", "pin": "123456"})

    async def test_register_phone_rejects_invalid_pin_before_meta_call(self):
        with self.assertRaises(HTTPException) as ctx:
            await _post_meta_phone_number_registration(
                phone_number_id="987654321",
                access_token="business-token",
                api_version="v21.0",
                pin="abc123",
            )
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(FakeAsyncClient.calls, [])

    async def test_register_phone_surfaces_meta_error(self):
        FakeAsyncClient.responses = [FakeResponse(400, {"error": {"message": "Invalid parameter"}})]
        with patch("app.services.whatsapp_service.httpx.AsyncClient", FakeAsyncClient):
            with self.assertRaises(HTTPException) as ctx:
                await _post_meta_phone_number_registration(
                    phone_number_id="987654321",
                    access_token="business-token",
                    api_version="v23.0",
                    pin="654321",
                )
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("Invalid parameter", str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main()
