import unittest
from datetime import datetime, timezone

from app.services.whatsapp_service import (
    _draft_missing_fields,
    _extract_fulfillment_from_whatsapp,
    _format_whatsapp_draft_followup,
    _format_whatsapp_transaction_confirmed,
    _is_whatsapp_cancel,
    _is_whatsapp_confirmation,
    _merge_whatsapp_order_context,
    normalize_phone,
)


class PhaseHWhatsAppAgentTests(unittest.TestCase):
    def _tenant(self):
        return {
            "name": "Cakkoo Fast Food",
            "settings": {
                "categoryHints": {
                    "fulfillment": {
                        "allowedTypes": ["delivery", "pickup"],
                        "defaultType": "delivery",
                    }
                }
            },
        }

    def _draft(self):
        return {
            "items": [
                {
                    "itemId": "64f000000000000000000001",
                    "name": "Spicy Zinger Burger",
                    "quantity": 2,
                    "unitPrice": 700,
                    "currency": "PKR",
                    "subtotal": 1400,
                    "canConfirm": True,
                }
            ],
            "pricing": {"total": 1400, "currency": "PKR"},
            "canConfirm": True,
            "confirmationIssues": [],
            "fulfillmentPreference": {"type": "none", "confidence": 0},
            "suggestedAt": datetime.now(timezone.utc),
        }

    def test_confirmation_and_cancel_keywords(self):
        self.assertTrue(_is_whatsapp_confirmation("g"))
        self.assertTrue(_is_whatsapp_confirmation("yes confirm kar do"))
        self.assertTrue(_is_whatsapp_confirmation("order confirm"))
        self.assertFalse(_is_whatsapp_confirmation("delivery"))
        self.assertTrue(_is_whatsapp_cancel("nahi chahiye cancel"))

    def test_fulfillment_extracts_delivery_address_and_city(self):
        fulfillment = _extract_fulfillment_from_whatsapp("House 12, Main Road, Attock")
        self.assertEqual(fulfillment["type"], "delivery")
        self.assertIn("House 12", fulfillment["address"]["line1"])
        self.assertEqual(fulfillment["address"]["city"], "Attock")

    def test_merge_context_adds_customer_and_missing_fields(self):
        draft = _merge_whatsapp_order_context(
            self._draft(),
            "delivery",
            customer_phone="03001234567",
            customer_name="Ali",
            tenant=self._tenant(),
        )
        self.assertEqual(draft["fulfillment"]["type"], "delivery")
        self.assertEqual(draft["customerSnapshot"]["phone"], normalize_phone("03001234567"))
        missing = _draft_missing_fields(draft, self._tenant())
        self.assertIn("delivery address", missing)
        self.assertIn("city", missing)

    def test_draft_followup_is_whatsapp_friendly(self):
        draft = _merge_whatsapp_order_context(self._draft(), "delivery", customer_phone="03001234567", tenant=self._tenant())
        text = _format_whatsapp_draft_followup(draft, self._tenant(), "roman_urdu")
        self.assertIn("address", text.lower())
        self.assertLessEqual(len(text), 250)

    def test_confirmed_transaction_message_is_short_and_clear(self):
        transaction = {
            "transactionNumber": "ORD-1001",
            "pricing": {"total": 1400},
            "items": [{"name": "Spicy Zinger Burger", "quantity": 2}],
        }
        text = _format_whatsapp_transaction_confirmed(transaction, "mixed")
        self.assertIn("ORD-1001", text)
        self.assertIn("1400", text)
        self.assertIn("✅", text)


if __name__ == "__main__":
    unittest.main()
