import unittest

from app.ai.agents.tools import classify_message_intent, rank_matching_items, score_item_match
from app.services.order_validation_service import normalize_fulfillment
from app.services.phase32_utils import is_short_confirmation, likely_food_or_unavailable_keywords, normalize_excel_header


class Phase32BugFixTests(unittest.TestCase):
    def test_excel_header_aliases_and_image_url(self):
        self.assertEqual(normalize_excel_header("Stock"), "stockQuantity")
        self.assertEqual(normalize_excel_header("Available Stock"), "stockQuantity")
        self.assertEqual(normalize_excel_header("Image URL"), "imageUrl")
        self.assertEqual(normalize_excel_header("Colour"), "color")

    def test_delivery_address_aliases_are_accepted(self):
        result = normalize_fulfillment({
            "type": "delivery",
            "address": {"addressLine1": "House 12", "addressCity": "Attock"},
        })
        self.assertEqual(result["type"], "delivery")
        self.assertEqual(result["address"]["line1"], "House 12")
        self.assertEqual(result["address"]["city"], "Attock")

    def test_confirmation_and_unavailable_helpers(self):
        self.assertTrue(is_short_confirmation("g bana do"))
        self.assertTrue(is_short_confirmation("haan"))
        self.assertTrue(likely_food_or_unavailable_keywords("burger hai?"))

    def test_catalog_matching_prefers_exact_color_size_product(self):
        message = "White sneakers size 42 hain?"
        hoodie = {
            "name": "Black Hoodie",
            "tags": ["black", "hoodie", "winter"],
            "description": "Warm black hoodie",
            "itemType": "product",
            "variants": [{"name": "Black Hoodie", "optionValues": {"color": "Black", "size": "Large"}}],
        }
        sneakers = {
            "name": "White Sneakers",
            "tags": ["white", "shoes", "sneakers"],
            "description": "Comfortable white sneakers",
            "itemType": "product",
            "variants": [{"name": "White 42", "optionValues": {"color": "White", "size": "42"}}],
        }
        self.assertGreater(score_item_match(message, sneakers), score_item_match(message, hoodie))
        ranked = rank_matching_items(message, [hoodie, sneakers])
        self.assertEqual(ranked[0]["name"], "White Sneakers")

    def test_availability_intent_detects_roman_urdu(self):
        result = classify_message_intent("White sneakers size 42 hain?", [])
        self.assertEqual(result["intent"], "ask_availability")


if __name__ == "__main__":
    unittest.main()
