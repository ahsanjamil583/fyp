import unittest

from bson import ObjectId

from app.services.ai_chat_service import build_draft_order, classify_message_intent, detect_language_mode


class AIChatTests(unittest.TestCase):
    def test_detect_language_mode_handles_mixed_language(self):
        self.assertEqual(detect_language_mode("burger ki price kya hai"), "mixed")

    def test_classify_message_intent_identifies_order_request(self):
        profile = classify_message_intent("2 burgers order kar do", [{"name": "Burger", "description": "", "tags": []}])
        self.assertEqual(profile["intent"], "place_order")
        self.assertGreaterEqual(profile["confidence"], 0.35)

    def test_build_draft_order_creates_tenant_safe_draft(self):
        tenant = {"_id": ObjectId()}
        matched_items = [
            {"_id": ObjectId(), "name": "Burger", "price": 450, "currency": "PKR", "itemType": "product", "isBookable": False, "isSellable": True},
        ]
        draft = build_draft_order(tenant, "2 burgers order kar do", matched_items, {"intent": "place_order"})
        self.assertEqual(draft["transactionType"], "order")
        self.assertEqual(draft["items"][0]["quantity"], 2)
        self.assertEqual(draft["items"][0]["unitPrice"], 450.0)

    def test_build_draft_order_requires_place_order_intent(self):
        tenant = {"_id": ObjectId()}
        matched_items = [
            {"_id": ObjectId(), "name": "Burger", "price": 450, "currency": "PKR", "itemType": "product", "isBookable": False, "isSellable": True},
        ]
        draft = build_draft_order(tenant, "burger ki price batao", matched_items, {"intent": "ask_price"})
        self.assertEqual(draft, {})
