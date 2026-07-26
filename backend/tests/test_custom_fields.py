import unittest

from app.services.custom_field_service import _validate_value_against_field


class CustomFieldValidationTests(unittest.TestCase):
    def test_required_text_field_returns_error_when_missing(self):
        field = {"key": "businessName", "label": "Business Name", "type": "text", "required": True, "validation": {}}
        errors = _validate_value_against_field(field, "")
        self.assertEqual(errors[0]["key"], "businessName")

    def test_select_field_requires_allowed_option(self):
        field = {"key": "plan", "label": "Plan", "type": "select", "required": False, "options": ["starter", "growth"], "validation": {}}
        errors = _validate_value_against_field(field, "scale")
        self.assertEqual(errors[0]["message"], "Plan must be one of the allowed options.")

    def test_number_field_enforces_range(self):
        field = {"key": "quantity", "label": "Quantity", "type": "number", "required": False, "validation": {"min": 1, "max": 5}}
        self.assertEqual(_validate_value_against_field(field, 3), [])
        self.assertTrue(_validate_value_against_field(field, 0))
