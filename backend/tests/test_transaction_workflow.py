import unittest

from fastapi import HTTPException

from app.services.transaction_workflow_service import (
    get_allowed_payment_statuses,
    get_initial_payment_status,
    get_initial_transaction_status,
    infer_transaction_type,
    normalize_transaction_type,
    validate_transaction_type_for_items,
)


class TransactionWorkflowTests(unittest.TestCase):
    def test_normalize_transaction_type_accepts_auto_as_none(self):
        self.assertIsNone(normalize_transaction_type("auto"))
        self.assertEqual(normalize_transaction_type("order"), "order")

    def test_infer_transaction_type_uses_inquiry_when_no_items(self):
        self.assertEqual(infer_transaction_type(None, []), "inquiry")

    def test_infer_transaction_type_uses_booking_for_bookable_items(self):
        item = {"itemType": "service", "isBookable": True}
        self.assertEqual(infer_transaction_type(None, [item]), "booking_request")

    def test_validate_booking_rejects_non_bookable_items(self):
        with self.assertRaises(HTTPException) as context:
            validate_transaction_type_for_items("booking_request", [{"itemType": "product", "isBookable": False}])
        self.assertEqual(context.exception.status_code, 422)

    def test_initial_status_and_payment_are_generalized(self):
        self.assertEqual(get_initial_transaction_status("quote_request"), "requested")
        self.assertEqual(get_initial_payment_status("inquiry"), "not_applicable")
        self.assertIn("quoted", get_allowed_payment_statuses("quote_request"))
