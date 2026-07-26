import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.services.ai_chat_service import build_system_prompt
from app.services.category_config_service import (
    apply_category_default_custom_fields,
    build_category_runtime_config,
    build_tenant_category_hints,
    hydrate_category_document,
    validate_tenant_fulfillment,
)


class CategoryConfigTests(unittest.IsolatedAsyncioTestCase):
    def test_hydrate_category_tolerates_legacy_malformed_metadata(self):
        category = hydrate_category_document(
            {
                "id": "legacy",
                "name": "Legacy Category",
                "slug": "legacy",
                "aiHints": "not-a-dict",
                "aiPromptFragments": "not-a-list",
                "analyticsSuggestions": "not-a-list",
                "websiteHints": "not-a-dict",
                "fulfillmentHints": "not-a-dict",
                "suggestedModules": "items",
                "defaultCustomFields": "bad",
            }
        )

        self.assertEqual(category["templateRules"]["recommendedTemplate"], "default")
        self.assertEqual(category["suggestedModules"], [])
        self.assertEqual(category["defaultCustomFields"], [])
        self.assertEqual(category["aiConfig"]["hints"]["businessPurpose"], "Help customers understand the business and next steps.")

    def test_build_category_runtime_config_derives_rules(self):
        category = {
            "name": "Clinic",
            "slug": "clinic",
            "websiteHints": {"recommendedTemplate": "service", "recommendedPrimaryColor": "#0F766E", "heroStyle": "trust-first"},
            "fulfillmentHints": {"defaultMode": "in_person_service", "supportsDelivery": False, "supportsPickup": False, "supportsInPerson": True},
            "analyticsSuggestions": ["Track service inquiry volume."],
            "aiHints": {"businessPurpose": "Provide clinic info."},
            "aiPromptFragments": ["Stay careful and non-diagnostic."],
        }
        runtime = build_category_runtime_config(category)
        self.assertEqual(runtime["templateRules"]["recommendedTemplate"], "service")
        self.assertEqual(runtime["fulfillmentRules"]["allowedTypes"], ["none"])
        self.assertIn("Track service inquiry volume.", runtime["analyticsConfig"]["suggestions"])
        self.assertIn("Stay careful and non-diagnostic.", runtime["aiConfig"]["promptFragments"])

    def test_validate_tenant_fulfillment_blocks_unsupported_type(self):
        tenant = {"settings": {"categoryHints": build_tenant_category_hints({
            "name": "Clinic",
            "slug": "clinic",
            "websiteHints": {"recommendedTemplate": "service"},
            "fulfillmentHints": {"defaultMode": "in_person_service", "supportsDelivery": False, "supportsPickup": False, "supportsInPerson": True},
        })}}
        with self.assertRaises(HTTPException) as context:
            validate_tenant_fulfillment(tenant, {"type": "delivery", "address": {"line1": "A", "city": "Lahore"}})
        self.assertEqual(context.exception.status_code, 422)

    async def test_apply_category_default_custom_fields_inserts_missing_defaults(self):
        tenant_oid = ObjectId()
        fake_collection = type("Collection", (), {"find_one": AsyncMock(return_value=None), "insert_one": AsyncMock()})()
        fake_db = type("FakeDb", (), {"custom_field_definitions": fake_collection})()
        category = {
            "defaultCustomFields": [
                {
                    "moduleCode": "transactions",
                    "entityType": "transaction",
                    "key": "service_slot",
                    "label": "Service Slot",
                    "type": "text",
                }
            ]
        }
        with patch("app.services.category_config_service.get_database", return_value=fake_db):
            await apply_category_default_custom_fields(tenant_oid, category)
        fake_collection.insert_one.assert_awaited_once()

    def test_build_system_prompt_contains_category_fragments(self):
        tenant = {
            "name": "Demo Clinic",
            "description": "Clinic",
            "contact": {"phone": "0300"},
            "settings": {"languageMode": "mixed"},
            "categoryConfig": {
                "name": "Clinic",
                "aiHints": {"businessPurpose": "Provide clinic info."},
                "aiPromptFragments": ["Avoid diagnosis.", "Encourage direct contact."],
                "fulfillmentRules": {"allowedTypes": ["none"]},
                "analyticsConfig": {"suggestions": ["Track inquiry volume."]},
            },
        }
        prompt = build_system_prompt(tenant, [], {}, {"intent": "general_info"}, "mixed")
        self.assertIn("Avoid diagnosis.", prompt)
        self.assertIn("Track inquiry volume.", prompt)
