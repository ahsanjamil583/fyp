"""Replies that must work without any LLM.

A greeting used to fall through every branch of the deterministic responder and reach
"I could not find this information in the business data", so the first message a
customer ever sent got the least useful answer the agent has. These cover the paths a
customer hits before any catalog term is mentioned.
"""

import unittest

from app.ai.agents.tools import (
    classify_message_intent,
    clean_customer_reply,
    detect_language_mode,
    format_business_summary,
    format_greeting_response,
    generate_rule_based_response,
    looks_like_about_business,
)

TENANT = {
    "name": "Style",
    "description": "Fashion is a dynamic expression of personal style and cultural identity.",
    "address": {"city": "attock"},
    "categoryConfig": {"name": "Fashion / Clothing"},
}
ITEMS = [
    {"name": "Green Winter Jacket", "price": 3500, "currency": "PKR"},
    {"name": "Black Denim Jeans", "price": 2800, "currency": "PKR"},
    {"name": "White Cotton T-Shirt", "price": 1200, "currency": "PKR"},
]
NO_MATCH = "could not find this information"


def _reply(message, all_items=ITEMS):
    profile = classify_message_intent(message, [])
    return generate_rule_based_response(
        TENANT, [], {}, profile, [], detect_language_mode(message), {"allowed": True, "flags": {}}, all_items
    )


class GreetingReplyTests(unittest.TestCase):
    def test_english_greeting_welcomes_and_names_real_products(self):
        reply = _reply("Hello")
        self.assertNotIn(NO_MATCH, reply)
        self.assertIn("Style", reply)
        self.assertIn("Green Winter Jacket", reply)

    def test_roman_urdu_greeting_answers_in_roman_urdu(self):
        reply = _reply("Assalam o Alaikum")
        self.assertNotIn(NO_MATCH, reply)
        self.assertIn("khush aamdeed", reply)

    def test_greeting_still_works_for_a_business_with_no_catalog(self):
        reply = _reply("Hi", all_items=[])
        self.assertNotIn(NO_MATCH, reply)
        self.assertIn("Style", reply)

    def test_about_the_business_describes_it(self):
        reply = _reply("Tell me about your business")
        self.assertNotIn(NO_MATCH, reply)
        self.assertIn("Fashion / Clothing", reply)
        self.assertIn("Black Denim Jeans", reply)
        # A free-typed onboarding city should not be shown lower case.
        self.assertIn("Attock", reply)

    def test_a_price_question_is_not_treated_as_a_greeting(self):
        profile = classify_message_intent("what is the price of jeans", [])
        self.assertNotEqual(profile["intent"], "greeting")
        self.assertFalse(looks_like_about_business(profile["normalizedText"]))

    def test_a_drafted_order_still_wins_over_a_greeting(self):
        profile = classify_message_intent("hello", [])
        draft = {"items": [{"name": "Black Denim Jeans", "quantity": 1, "unitPrice": 2800, "lineTotal": 2800}], "currency": "PKR"}
        reply = generate_rule_based_response(TENANT, [], draft, profile, [], "english", {"allowed": True, "flags": {}}, ITEMS)
        self.assertIn("Black Denim Jeans", reply)
        self.assertNotIn("Welcome to Style", reply)


class LanguageDetectionTests(unittest.TestCase):
    def test_urdu_greetings_are_not_read_as_english(self):
        for message in ["Assalam o Alaikum", "salam", "aoa"]:
            self.assertIn(detect_language_mode(message), {"roman_urdu", "mixed"}, message)

    def test_plain_english_stays_english(self):
        for message in ["Hello", "What is the price", "show me available items"]:
            self.assertEqual(detect_language_mode(message), "english", message)


class WhatsAppFormattingTests(unittest.TestCase):
    def test_markdown_bold_becomes_whatsapp_bold(self):
        self.assertEqual(clean_customer_reply("**Style Fashion**", "whatsapp"), "*Style Fashion*")

    def test_a_long_line_is_trimmed_on_a_word_boundary(self):
        reply = clean_customer_reply("word " * 60, "whatsapp")
        self.assertTrue(reply.endswith("..."))
        self.assertNotIn("wor.", reply)

    def test_a_short_reply_is_left_alone(self):
        self.assertEqual(clean_customer_reply("Price: PKR 2800", "whatsapp"), "Price: PKR 2800")


class BusinessSummaryTests(unittest.TestCase):
    def test_summary_survives_a_business_with_no_description_or_city(self):
        reply = format_business_summary({"name": "Shop"}, [], "english")
        self.assertIn("Shop", reply)
        self.assertNotIn("None", reply)

    def test_greeting_survives_a_tenant_with_no_name(self):
        self.assertTrue(format_greeting_response({}, [], "english"))


if __name__ == "__main__":
    unittest.main()
