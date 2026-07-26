import unittest

from bson import ObjectId

from app.db.seeders.seed_business_categories import default_business_categories
from app.services.onboarding_service import (
    build_launch_checks,
    build_launch_payment_defaults,
    build_launch_report_defaults,
    build_launch_whatsapp_defaults,
    highest_required_plan,
    normalize_launch_profile,
    summarize_launch_status,
)
from app.services.qa_service import _phase28_finalized


class Phase28OnboardingTests(unittest.TestCase):
    def test_default_business_categories_include_common_setup_options(self):
        names = {category["name"] for category in default_business_categories()}

        for expected in {
            "Retail Store",
            "Restaurant",
            "Pharmacy",
            "Fashion / Clothing",
            "Services",
            "Grocery",
            "Electronics",
            "Beauty / Salon",
            "Tailor",
            "General Business",
        }:
            self.assertIn(expected, names)

    def test_normalize_launch_profile_uses_default_for_unknown_profile(self):
        self.assertEqual(normalize_launch_profile("full_agent_demo"), "full_agent_demo")
        self.assertEqual(normalize_launch_profile("unknown"), "ai_ordering")

    def test_highest_required_plan_does_not_downgrade_current_plan(self):
        self.assertEqual(highest_required_plan("scale", "growth"), "scale")
        self.assertEqual(highest_required_plan("starter", "growth"), "growth")
        self.assertEqual(highest_required_plan("bad", "scale"), "scale")

    def test_summarize_launch_status_requires_required_checks_only_for_publish(self):
        checks = [
            {"required": True, "completed": True},
            {"required": True, "completed": True},
            {"required": False, "completed": False},
        ]
        summary = summarize_launch_status(checks, {"websiteStatus": "draft", "status": "draft"})
        self.assertEqual(summary["requiredPercent"], 100)
        self.assertTrue(summary["canPublish"])
        self.assertEqual(summary["status"], "ready_to_publish")

    def test_launch_profile_default_builders_create_live_service_settings(self):
        tenant_id = ObjectId()
        user_id = ObjectId()
        tenant = {
            "_id": tenant_id,
            "name": "Demo Shop",
            "contact": {"phone": "03001111111", "whatsapp": "03001111111"},
            "settings": {"timezone": "Asia/Karachi", "languageMode": "mixed"},
        }

        payment = build_launch_payment_defaults(tenant_id, user_id)
        reports = build_launch_report_defaults(tenant_id, tenant)
        whatsapp = build_launch_whatsapp_defaults(tenant_id, tenant)

        self.assertTrue(payment["codEnabled"])
        self.assertTrue(payment["manualEnabled"])
        self.assertEqual(payment["defaultMethod"], "cod")
        self.assertTrue(reports["enabled"])
        self.assertTrue(reports["whatsappEnabled"])
        self.assertEqual(reports["whatsappRecipient"], "+923001111111")
        self.assertEqual(whatsapp["provider"], "mock")
        self.assertTrue(whatsapp["isConnected"])
        self.assertEqual(whatsapp["status"], "connected_mock")

    def test_ordering_check_requires_payment_settings_and_enabled_method(self):
        tenant = {
            "name": "Demo",
            "businessCategoryId": ObjectId(),
            "description": "Demo business",
            "contact": {"phone": "+923001111111"},
            "address": {"city": "Attock", "province": "Punjab"},
            "websiteSettings": {"templateCode": "catalog"},
        }
        category = {"suggestedModules": ["items", "website_builder", "customer_portal", "ai_chat", "payments"]}
        enabled = {"items", "website_builder", "customer_portal", "ai_chat", "payments"}
        counts = {"sellableItems": 1, "activeItems": 1, "knowledgeDocuments": 1, "paymentSettings": 0, "localPaymentsEnabled": False}

        checks = build_launch_checks(tenant, category, enabled, counts)
        ordering = next(check for check in checks if check["code"] == "ordering_ready")
        self.assertFalse(ordering["completed"])

        counts["paymentSettings"] = 1
        counts["localPaymentsEnabled"] = True
        checks = build_launch_checks(tenant, category, enabled, counts)
        ordering = next(check for check in checks if check["code"] == "ordering_ready")
        self.assertTrue(ordering["completed"])

    def test_final_qa_recognizes_phase28_onboarding_metadata(self):
        tenant = {"settings": {"onboarding": {"phase28": {"finalizedAt": "2026-07-02T10:00:00+00:00"}}}}
        self.assertTrue(_phase28_finalized(tenant))
