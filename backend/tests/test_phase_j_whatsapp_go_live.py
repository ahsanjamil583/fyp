import unittest

from app.schemas.whatsapp_schema import WhatsAppGoLiveTestRunRequest
from app.services.whatsapp_service import _phase_j_check, _phase_j_test_result_from_payload


class PhaseJWhatsAppGoLiveTests(unittest.TestCase):
    def test_phase_j_check_statuses(self):
        self.assertEqual(_phase_j_check("ok", "OK", True, "ready")["status"], "pass")
        self.assertEqual(_phase_j_check("warn", "Warn", False, "later", severity="warning")["status"], "warn")
        self.assertEqual(_phase_j_check("fail", "Fail", False, "missing")["status"], "fail")

    def test_auto_result_passes_when_required_live_flow_passed(self):
        payload = WhatsAppGoLiveTestRunRequest(
            realCustomerMessageReceived=True,
            aiReplyDelivered=True,
            conversationVisible=True,
            orderFlowTested=True,
            orderCreated=True,
        )
        self.assertEqual(_phase_j_test_result_from_payload(payload), "passed")

    def test_auto_result_warns_for_reply_without_advanced_tests(self):
        payload = WhatsAppGoLiveTestRunRequest(
            realCustomerMessageReceived=True,
            aiReplyDelivered=True,
            conversationVisible=True,
        )
        self.assertEqual(_phase_j_test_result_from_payload(payload), "warning")

    def test_manual_result_override(self):
        payload = WhatsAppGoLiveTestRunRequest(result="failed")
        self.assertEqual(_phase_j_test_result_from_payload(payload), "failed")


if __name__ == "__main__":
    unittest.main()
