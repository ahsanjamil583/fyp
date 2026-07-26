import unittest

from app.schemas.whatsapp_schema import WhatsAppLiveWebhookTestRequest
from app.services.whatsapp_service import _extract_meta_whatsapp_message_events, _phase_i_check


class PhaseIWhatsAppDashboardTests(unittest.TestCase):
    def test_phase_i_check_statuses(self):
        self.assertEqual(_phase_i_check("provider", "Provider", True, "ok")["status"], "pass")
        self.assertEqual(_phase_i_check("recent", "Recent", False, "none", severity="warning")["status"], "warn")
        self.assertEqual(_phase_i_check("token", "Token", False, "missing")["status"], "fail")

    def test_live_webhook_test_request_defaults_are_safe(self):
        payload = WhatsAppLiveWebhookTestRequest()
        self.assertFalse(payload.processWithAgent)
        self.assertIn("Zinger", payload.messageText)

    def test_meta_webhook_test_shape_is_supported(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba-1",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"display_phone_number": "923001111111", "phone_number_id": "phone-1"},
                                "contacts": [{"wa_id": "923009999999", "profile": {"name": "Live Test"}}],
                                "messages": [
                                    {"from": "923009999999", "id": "phase-i", "type": "text", "text": {"body": "Menu bhej do"}}
                                ],
                            },
                        }
                    ],
                }
            ],
        }
        events = _extract_meta_whatsapp_message_events(payload)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["phoneNumberId"], "phone-1")
        self.assertEqual(events[0]["messageText"], "Menu bhej do")


if __name__ == "__main__":
    unittest.main()
