import unittest

from app.services.whatsapp_service import (
    _extract_meta_whatsapp_message_events,
    _extract_meta_whatsapp_status_events,
    normalize_phone,
)


class PhaseGWhatsAppRoutingTests(unittest.TestCase):
    def test_extracts_message_events_with_phone_number_id(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba-1",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {
                                    "display_phone_number": "923001111111",
                                    "phone_number_id": "phone-number-123",
                                },
                                "contacts": [
                                    {"wa_id": "923009999999", "profile": {"name": "Danyal"}},
                                ],
                                "messages": [
                                    {
                                        "from": "923009999999",
                                        "id": "wamid.abc",
                                        "type": "text",
                                        "text": {"body": "Zinger burger available hai?"},
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }

        events = _extract_meta_whatsapp_message_events(payload)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["phoneNumberId"], "phone-number-123")
        self.assertEqual(events[0]["displayPhoneNumber"], "923001111111")
        self.assertEqual(events[0]["fromPhone"], "923009999999")
        self.assertEqual(events[0]["customerName"], "Danyal")
        self.assertEqual(events[0]["messageText"], "Zinger burger available hai?")
        self.assertEqual(events[0]["providerMessageId"], "wamid.abc")

    def test_extracts_button_and_interactive_text(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "p-1"},
                                "messages": [
                                    {"from": "923001", "id": "m1", "type": "button", "button": {"text": "Confirm order"}},
                                    {
                                        "from": "923002",
                                        "id": "m2",
                                        "type": "interactive",
                                        "interactive": {"type": "list_reply", "list_reply": {"title": "Pickup"}},
                                    },
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        events = _extract_meta_whatsapp_message_events(payload)
        self.assertEqual([event["messageText"] for event in events], ["Confirm order", "Pickup"])

    def test_extracts_status_events_for_delivery_updates(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone-number-123", "display_phone_number": "923001111111"},
                                "statuses": [
                                    {"id": "wamid.out", "recipient_id": "923009999999", "status": "delivered", "timestamp": "1710000000"}
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        events = _extract_meta_whatsapp_status_events(payload)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["phoneNumberId"], "phone-number-123")
        self.assertEqual(events[0]["providerMessageId"], "wamid.out")
        self.assertEqual(events[0]["status"], "delivered")

    def test_normalize_phone_keeps_pakistan_business_number_consistent(self):
        self.assertEqual(normalize_phone("0300 1234567"), "+923001234567")
        self.assertEqual(normalize_phone("923001234567"), "+923001234567")


if __name__ == "__main__":
    unittest.main()
