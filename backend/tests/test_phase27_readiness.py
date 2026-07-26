import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi.testclient import TestClient


class Phase27ReadinessTests(unittest.TestCase):
    def test_readiness_route_returns_phase27_report(self):
        fake_report = {
            "overallStatus": "ready_with_warnings",
            "totals": {"pass": 7, "warn": 2, "fail": 0},
            "checks": [{"code": "mongodb", "label": "MongoDB connection", "status": "pass", "message": "ok"}],
            "runtime": {"appVersion": "0.27.0", "buildLabel": "phase-27-final-hardening"},
            "services": {},
            "integrations": {},
        }
        with (
            patch("app.main.connect_to_mongo", new=AsyncMock()),
            patch("app.main.close_mongo_connection", new=AsyncMock()),
            patch("app.main.create_indexes", new=AsyncMock()),
            patch("app.main.seed_default_admin", new=AsyncMock()),
            patch("app.main.seed_modules", new=AsyncMock()),
            patch("app.main.seed_business_categories", new=AsyncMock()),
            patch("app.api.v1.health_routes.build_readiness_report", new=AsyncMock(return_value=fake_report)),
        ):
            from app.main import create_app

            app = create_app()
            with TestClient(app) as client:
                response = client.get("/api/v1/health/readiness")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["runtime"]["appVersion"], "0.27.0")
        self.assertIn("X-Request-ID", response.headers)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_demo_accounts_route_is_available_for_demo_setup(self):
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
                response = client.get("/api/v1/health/demo-accounts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["businessSlug"], "demo-bazaar")


class Phase27SystemValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_report_includes_demo_seed_status(self):
        from app.services.system_validation_service import build_readiness_report

        fake_mongo = {"connected": True}
        fake_demo_seed = {
            "available": True,
            "message": "Demo seed data is ready.",
            "counts": {"tenant": 1, "activeItems": 3, "paymentSettings": 1, "reportSettings": 1, "whatsappIntegrations": 1},
        }
        writable = {"path": "tmp", "exists": True, "writable": True}
        with (
            patch("app.services.system_validation_service.get_mongo_status", new=AsyncMock(return_value=fake_mongo)),
            patch("app.services.system_validation_service.chroma_client.status", return_value={"mode": "persistent"}),
            patch("app.services.system_validation_service._directory_status", return_value=writable),
            patch("app.services.system_validation_service._demo_seed_status", new=AsyncMock(return_value=fake_demo_seed)),
        ):
            report = await build_readiness_report()

        check_by_code = {check["code"]: check for check in report["checks"]}
        self.assertIn("demo_seed", check_by_code)
        self.assertEqual(check_by_code["demo_seed"]["status"], "pass")
        self.assertEqual(report["services"]["demoSeed"]["counts"]["paymentSettings"], 1)

    def test_demo_seed_builders_create_live_service_settings(self):
        from scripts.seed_demo_data import (
            DEMO_OWNER_PHONE,
            build_demo_payment_settings,
            build_demo_report_delivery_settings,
            build_demo_whatsapp_integration,
        )

        tenant_id = ObjectId()
        owner_id = ObjectId()
        payment = build_demo_payment_settings(tenant_id, owner_id)
        reports = build_demo_report_delivery_settings(tenant_id)
        whatsapp = build_demo_whatsapp_integration(tenant_id)

        self.assertTrue(payment["codEnabled"])
        self.assertTrue(payment["manualEnabled"])
        self.assertTrue(payment["jazzCashEnabled"])
        self.assertEqual(payment["defaultMethod"], "cod")
        self.assertTrue(reports["enabled"])
        self.assertTrue(reports["whatsappEnabled"])
        self.assertEqual(reports["whatsappRecipient"], DEMO_OWNER_PHONE)
        self.assertEqual(whatsapp["provider"], "mock")
        self.assertTrue(whatsapp["isConnected"])
        self.assertEqual(whatsapp["normalizedBusinessWhatsAppNumber"], DEMO_OWNER_PHONE)
