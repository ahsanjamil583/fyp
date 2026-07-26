import unittest

from fastapi import HTTPException

from app.services.localization_service import (
    build_ai_localization_guidance,
    evaluate_localized_reply,
    normalize_optional_pk_phone_or_blank,
    normalize_pk_phone,
    normalize_province,
)


class LocalizationTests(unittest.TestCase):
    def test_phone_normalization_accepts_pakistan_formats(self):
        self.assertEqual(normalize_pk_phone("+923001234567"), "03001234567")
        self.assertEqual(normalize_pk_phone("0300 1234567"), "03001234567")

    def test_phone_normalization_rejects_invalid_input(self):
        with self.assertRaises(HTTPException) as context:
            normalize_pk_phone("12345")
        self.assertEqual(context.exception.status_code, 422)

    def test_phone_normalization_can_ignore_legacy_invalid_values_when_needed(self):
        self.assertEqual(normalize_optional_pk_phone_or_blank("12345"), "")
        self.assertEqual(normalize_optional_pk_phone_or_blank("+923001234567"), "03001234567")

    def test_province_normalization_requires_pakistan_values(self):
        self.assertEqual(normalize_province("punjab"), "Punjab")
        with self.assertRaises(HTTPException):
            normalize_province("California")

    def test_ai_localization_guidance_uses_local_hints(self):
        guidance = build_ai_localization_guidance(
            "roman_urdu",
            {"address": {"city": "Lahore", "province": "Punjab"}, "contact": {"whatsapp": "03001234567"}},
        )
        self.assertIn("Lahore", guidance)
        self.assertIn("03001234567", guidance)

    def test_localized_reply_evaluation_rewards_clear_localized_reply(self):
        result = evaluate_localized_reply(
            "burger ki qeemat kya hai",
            "Ji, burger ki price PKR 450 hai. Agar chahiye ho to WhatsApp par confirm kar dein.",
            "mixed",
            "ask_price",
        )
        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["score"], 0.75)
