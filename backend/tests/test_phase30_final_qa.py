import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.qa_service import (
    build_demo_run_coverage,
    build_phase_summary,
    build_qa_next_actions,
    normalize_checked_steps,
    normalize_demo_result,
    summarize_qa_checks,
)


class Phase30FinalQaTests(unittest.TestCase):
    def test_phase_summary_reports_phase_30(self):
        summary = build_phase_summary()
        self.assertGreaterEqual(summary["implementedThrough"], 30)
        self.assertTrue(any(item["phase"] == 30 for item in summary["phaseSummary"]))

    def test_summarize_qa_checks_detects_blocking_failures(self):
        checks = [
            {"status": "pass", "required": True},
            {"status": "warn", "required": False},
            {"status": "fail", "required": True, "code": "catalog_ready"},
        ]
        summary = summarize_qa_checks(checks)
        self.assertEqual(summary["status"], "needs_fixes")
        self.assertEqual(summary["totals"]["fail"], 1)
        self.assertEqual(summary["blockingGaps"][0]["code"], "catalog_ready")
        self.assertEqual(summary["nextActions"][0]["code"], "catalog_ready")

    def test_next_actions_prioritize_required_failures_then_warnings(self):
        checks = [
            {"status": "warn", "required": False, "code": "whatsapp_agent", "title": "WhatsApp", "route": "/dashboard/whatsapp-agent", "description": "Connect WhatsApp."},
            {"status": "fail", "required": True, "code": "catalog_ready", "title": "Catalog", "route": "/dashboard/items", "description": "Add items."},
        ]
        actions = build_qa_next_actions(checks)
        self.assertEqual(actions[0]["code"], "catalog_ready")
        self.assertEqual(actions[1]["code"], "whatsapp_agent")

    def test_demo_run_coverage_normalizes_duplicate_and_invalid_steps(self):
        self.assertEqual(normalize_checked_steps([1, "2", 2, 99, "bad"]), [1, 2])
        coverage = build_demo_run_coverage([1, 2])
        self.assertEqual(coverage["checkedCount"], 2)
        self.assertGreater(coverage["totalSteps"], 2)
        self.assertTrue(coverage["missingSteps"])

    def test_normalize_demo_result_accepts_only_expected_values(self):
        self.assertEqual(normalize_demo_result("PASS"), "pass")
        with self.assertRaises(HTTPException):
            normalize_demo_result("maybe")

    def test_phase_summary_route_is_public_for_smoke_check(self):
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
                response = client.get("/api/v1/health/phase-summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertGreaterEqual(payload["data"]["implementedThrough"], 30)

    def test_public_phase_summary_contains_demo_steps(self):
        summary = build_phase_summary()
        self.assertGreaterEqual(len(summary["recommendedDemoOrder"]), 5)
        self.assertIn("WhatsApp", " ".join(summary["recommendedDemoOrder"]))
