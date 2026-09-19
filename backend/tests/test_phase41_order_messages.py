"""Phase 41: order confirmations and the order receipt.

Weighted towards the ways a confirmation system goes wrong in production: sending twice,
sending to nobody, sending into a channel that silently drops it, blocking an order
because a mail server was slow, and leaking internal data into a document the customer
forwards to other people.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.services import order_message_service as messages
from app.services.order_message_service import (
    CHANNEL_EMAIL,
    CHANNEL_WHATSAPP,
    EVENT_ORDER_PLACED,
    EVENT_PAYMENT_CONFIRMED,
    build_message_content,
    receipt_url,
    resolve_recipients,
    serialize_message_settings,
)
from app.services.order_receipt_service import build_order_receipt_html

TENANT = {
    "_id": ObjectId(),
    "name": "Demo Bazaar",
    "contact": {"phone": "03001112222"},
    "address": {"line1": "12 Mall Road", "city": "Lahore"},
}


def order(**overrides):
    base = {
        "_id": ObjectId(),
        "tenantId": TENANT["_id"],
        "transactionNumber": "ORD-20260916-00007",
        "source": "customer_portal",
        "status": "pending",
        "paymentStatus": "unpaid",
        "receiptToken": "tok_abc123",
        "items": [
            {"name": "Classic Black Shoes", "quantity": 2, "unitPrice": 3999.0, "subtotal": 7998.0,
             "currency": "PKR", "selectedVariantName": "Black / 42", "costPrice": 1500.0,
             "stockSnapshot": {"availableQuantity": 7}},
        ],
        "pricing": {"subtotal": 7998.0, "discount": 0, "tax": 0, "total": 7998.0, "currency": "PKR"},
        "customerSnapshot": {"name": "Sara Khan", "phone": "03001234567", "email": "sara@example.com"},
        "fulfillment": {"type": "delivery", "address": {"line1": "9 Model Town", "city": "Lahore"}},
        "notes": "Please call before delivery",
        "internalNotes": "owner only - VIP",
    }
    base.update(overrides)
    return base


class RecipientTests(unittest.TestCase):
    def test_the_order_snapshot_is_the_source_of_truth(self):
        """It is the one field populated for signed-in customers and guests alike."""
        people = resolve_recipients(order())
        self.assertEqual(people["email"], "sara@example.com")
        self.assertEqual(people["phone"], "03001234567")
        self.assertEqual(people["name"], "Sara Khan")

    def test_a_missing_address_resolves_to_blank_rather_than_raising(self):
        people = resolve_recipients(order(customerSnapshot={"name": "Guest"}))
        self.assertEqual(people["email"], "")
        self.assertEqual(people["phone"], "")

    def test_a_malformed_phone_is_dropped_not_sent_to(self):
        people = resolve_recipients(order(customerSnapshot={"phone": "not-a-number"}))
        self.assertEqual(people["phone"], "")

    def test_an_international_format_phone_is_normalised(self):
        people = resolve_recipients(order(customerSnapshot={"phone": "+92 300 1234567"}))
        self.assertEqual(people["phone"], "03001234567")


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.people = resolve_recipients(order())

    def test_the_placed_message_names_the_order_and_total(self):
        content = build_message_content(EVENT_ORDER_PLACED, TENANT, order(), self.people, "https://x/r/tok")
        self.assertIn("ORD-20260916-00007", content["subject"])
        self.assertIn("PKR 7,998.00", content["text"])
        self.assertIn("https://x/r/tok", content["text"])
        self.assertIn("Classic Black Shoes", content["text"])

    def test_the_variant_appears_on_the_line(self):
        content = build_message_content(EVENT_ORDER_PLACED, TENANT, order(), self.people, "https://x/r/tok")
        self.assertIn("Black / 42", content["itemLines"])

    def test_the_payment_message_is_a_different_message(self):
        placed = build_message_content(EVENT_ORDER_PLACED, TENANT, order(), self.people, "https://x/r/tok")
        paid = build_message_content(EVENT_PAYMENT_CONFIRMED, TENANT, order(paymentStatus="paid"), self.people, "https://x/r/tok")
        self.assertNotEqual(placed["subject"], paid["subject"])
        self.assertIn("payment", paid["subject"].lower())
        self.assertIn("marked as paid", paid["statusLine"])

    def test_an_unpaid_order_is_told_how_to_pay(self):
        content = build_message_content(EVENT_ORDER_PLACED, TENANT, order(), self.people, "https://x/r/tok")
        self.assertIn("complete payment", content["statusLine"].lower())

    def test_a_paid_order_is_not_asked_to_pay_again(self):
        content = build_message_content(EVENT_ORDER_PLACED, TENANT, order(paymentStatus="paid"), self.people, "https://x/r/tok")
        self.assertIn("complete", content["statusLine"].lower())
        self.assertNotIn("complete payment from", content["statusLine"].lower())

    def test_the_whatsapp_version_is_short_and_plain(self):
        content = build_message_content(EVENT_ORDER_PLACED, TENANT, order(), self.people, "https://x/r/tok")
        self.assertLess(len(content["whatsapp"]), 700)
        self.assertNotIn("<", content["whatsapp"])
        self.assertIn("https://x/r/tok", content["whatsapp"])

    def test_a_nameless_customer_still_gets_a_greeting(self):
        people = resolve_recipients(order(customerSnapshot={"email": "x@example.com"}))
        content = build_message_content(EVENT_ORDER_PLACED, TENANT, order(), people, "https://x/r/tok")
        self.assertTrue(content["text"].startswith("Hi,"))

    def test_the_owner_footer_note_is_included_when_set(self):
        content = build_message_content(
            EVENT_ORDER_PLACED, TENANT, order(), self.people, "https://x/r/tok", "Open 9am to 9pm."
        )
        self.assertIn("Open 9am to 9pm.", content["text"])

    def test_no_internal_field_reaches_the_message(self):
        content = build_message_content(EVENT_ORDER_PLACED, TENANT, order(), self.people, "https://x/r/tok")
        blob = content["text"] + content["whatsapp"]
        self.assertNotIn("owner only", blob)
        self.assertNotIn("1500", blob)
        self.assertNotIn(str(order()["_id"]), blob)


class ReceiptLinkTests(unittest.TestCase):
    def test_the_link_points_at_the_api_that_renders_it(self):
        """There is no page in the React app at /receipts/:token, so a frontend URL
        would have 404'd for every customer who clicked it."""
        link = receipt_url("tok_abc123")
        self.assertIn("/api/v1/receipts/tok_abc123", link)


class ReceiptRenderingTests(unittest.TestCase):
    def setUp(self):
        self.html = build_order_receipt_html(TENANT, order())

    def test_it_shows_what_a_receipt_must_show(self):
        for expected in ("Demo Bazaar", "ORD-20260916-00007", "Classic Black Shoes",
                         "Black / 42", "PKR 7,998.00", "Sara Khan"):
            self.assertIn(expected, self.html, expected)

    def test_an_unpaid_order_is_not_stamped_paid(self):
        self.assertNotIn(">Paid<", self.html)

    def test_a_paid_order_is_stamped_paid(self):
        html = build_order_receipt_html(TENANT, order(paymentStatus="paid"))
        self.assertIn("Paid", html)

    def test_it_leaks_no_owner_only_data(self):
        """A receipt gets forwarded. Cost price and internal notes must not travel."""
        self.assertNotIn("owner only", self.html)
        self.assertNotIn("1500", self.html)
        self.assertNotIn("availableQuantity", self.html)

    def test_it_does_not_expose_the_database_id(self):
        self.assertNotIn(str(order()["_id"]), self.html)

    def test_customer_supplied_text_is_escaped(self):
        """The name and the note come from a customer and are rendered as HTML."""
        hostile = order(
            customerSnapshot={"name": "<script>alert(1)</script>", "phone": "", "email": ""},
            notes="<img src=x onerror=alert(1)>",
        )
        html = build_order_receipt_html(TENANT, hostile)
        # What matters is that neither becomes a tag or an attribute. The literal text
        # "onerror=" still appears, but only inside an escaped, inert string.
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)

    def test_it_carries_its_own_print_rules(self):
        """It is opened from an email, where no stylesheet of ours will load."""
        self.assertIn("@media print", self.html)

    def test_an_order_with_no_items_still_renders(self):
        html = build_order_receipt_html(TENANT, order(items=[]))
        self.assertIn("No items recorded", html)


class SettingsTests(unittest.TestCase):
    def test_a_business_that_never_configured_anything_still_confirms(self):
        config = serialize_message_settings(None, TENANT["_id"])
        self.assertTrue(config["emailEnabled"])
        self.assertTrue(config["whatsappEnabled"])
        self.assertTrue(config["sendOnOrderPlaced"])
        self.assertTrue(config["sendOnPaymentConfirmed"])

    def test_stored_values_win_over_the_defaults(self):
        config = serialize_message_settings(
            {"emailEnabled": False, "whatsappEnabled": False, "sendOnPaymentConfirmed": False}, TENANT["_id"]
        )
        self.assertFalse(config["emailEnabled"])
        self.assertFalse(config["whatsappEnabled"])
        self.assertFalse(config["sendOnPaymentConfirmed"])

    def test_the_footer_note_is_bounded(self):
        config = serialize_message_settings({"footerNote": "x" * 900}, TENANT["_id"])
        self.assertEqual(len(config["footerNote"]), 300)


class WhatsAppReachabilityTests(unittest.IsolatedAsyncioTestCase):
    """send_whatsapp_text always succeeds at writing its log row, so the only useful
    question is whether anything would ever collect it."""

    async def _reachable(self, integration):
        integrations = AsyncMock()
        integrations.find_one.return_value = integration
        fake_db = type("DB", (), {"whatsapp_integrations": integrations})()
        with patch.object(messages, "get_database", return_value=fake_db):
            return await messages.whatsapp_is_reachable(TENANT["_id"])

    async def test_a_connected_bridge_is_reachable(self):
        """The fixture is a real integration document. `connectionStatus` is derived on
        the API response and never stored, so a test that injects it proves nothing."""
        ok, _ = await self._reachable(
            {
                "provider": "baileys",
                "isConnected": True,
                "bridgeStatus": "ready",
                "bridgeLastSeenAt": datetime.now(timezone.utc),
            }
        )
        self.assertTrue(ok)

    async def test_mock_mode_is_not_reachable(self):
        ok, why = await self._reachable({"provider": "mock", "isConnected": True, "bridgeStatus": "ready"})
        self.assertFalse(ok)
        self.assertIn("mock", why)

    async def test_a_bridge_that_never_paired_is_not_reachable(self):
        ok, why = await self._reachable({"provider": "baileys", "isConnected": False})
        self.assertFalse(ok)
        self.assertIn("not configured", why)

    async def test_a_paired_bridge_that_stopped_reporting_is_not_reachable(self):
        """A bridge that has gone quiet for more than 90 seconds is not paired any more,
        and its queued rows would never be collected."""
        ok, why = await self._reachable(
            {
                "provider": "baileys",
                "isConnected": True,
                "bridgeStatus": "ready",
                "bridgeLastSeenAt": datetime.now(timezone.utc) - timedelta(hours=2),
            }
        )
        self.assertFalse(ok)
        self.assertIn("awaiting bridge", why)

    async def test_no_integration_at_all_is_not_reachable(self):
        ok, why = await self._reachable(None)
        self.assertFalse(ok)
        self.assertIn("no WhatsApp integration", why)


class IdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_claim_is_written_before_anything_is_sent(self):
        """Claiming after sending would leave a window for a replayed callback to send a
        second copy while the first was still in flight."""
        import inspect

        source = inspect.getsource(messages.send_order_message)
        claim_position = source.index("_claim_delivery")
        # The send now goes through asyncio.to_thread, because smtplib blocks for up to
        # 20 seconds and was stalling the whole event loop inside order creation.
        send_position = source.index("send_order_email")
        self.assertLess(claim_position, send_position)
        self.assertIn("asyncio.to_thread", source)

    async def test_a_duplicate_claim_is_refused(self):
        collection = AsyncMock()
        collection.insert_one.side_effect = DuplicateKeyError("dup")
        fake_db = {messages.DELIVERY_COLLECTION: collection}
        with patch.object(messages, "get_database", return_value=fake_db):
            claimed = await messages._claim_delivery(order(), EVENT_ORDER_PLACED, CHANNEL_EMAIL, "sara@example.com")
        self.assertFalse(claimed)

    async def test_a_first_claim_succeeds(self):
        collection = AsyncMock()
        collection.insert_one.return_value = None
        fake_db = {messages.DELIVERY_COLLECTION: collection}
        with patch.object(messages, "get_database", return_value=fake_db):
            claimed = await messages._claim_delivery(order(), EVENT_ORDER_PLACED, CHANNEL_EMAIL, "sara@example.com")
        self.assertTrue(claimed)

    def test_the_uniqueness_is_enforced_by_an_index(self):
        """A code-level check alone would not survive two workers."""
        import inspect

        from app.db import indexes

        source = inspect.getsource(indexes.create_indexes)
        self.assertIn("order_message_deliveries", source)
        self.assertIn("order_message_once", source)


class NeverBreakTheOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_an_unhandled_failure_is_swallowed_by_the_entry_points(self):
        """The hooks run inside order creation. Raising would undo a real order."""
        with patch.object(messages, "send_order_message", side_effect=RuntimeError("smtp exploded")):
            placed = await messages.notify_order_placed(order())
            paid = await messages.notify_payment_confirmed(order(paymentStatus="paid"))
        self.assertEqual(placed["failed"][0]["reason"], "unhandled")
        self.assertEqual(paid["failed"][0]["reason"], "unhandled")

    async def test_an_unpaid_order_never_gets_a_payment_confirmation(self):
        with patch.object(messages, "send_order_message", new=AsyncMock()) as sender:
            result = await messages.notify_payment_confirmed(order(paymentStatus="unpaid"))
        sender.assert_not_awaited()
        self.assertEqual(result["skipped"][0]["reason"], "not paid")

    async def test_cash_on_delivery_is_not_a_payment_confirmation(self):
        """COD is settled for the order's purposes but no money has moved."""
        with patch.object(messages, "send_order_message", new=AsyncMock()) as sender:
            await messages.notify_payment_confirmed(order(paymentStatus="cod"))
        sender.assert_not_awaited()

    async def test_counter_and_imported_orders_are_never_messaged(self):
        for source in ("cashier", "imported"):
            report = await messages.send_order_message(order(source=source), EVENT_ORDER_PLACED, TENANT)
            self.assertFalse(report["sent"], source)
            self.assertIn(source, report["skipped"][0]["reason"])


class HookWiringTests(unittest.TestCase):
    def test_every_online_order_path_triggers_a_confirmation(self):
        import inspect

        from app.services import customer_portal_service, public_website_service

        # The customer path announces through a helper so that a failing notification
        # cannot abort an order that has already been placed, so follow the call chain
        # rather than looking for the name in one function body.
        builder = inspect.getsource(customer_portal_service._build_transaction_from_items)
        self.assertIn("_announce_new_transaction", builder)
        self.assertIn("notify_order_placed", inspect.getsource(customer_portal_service._announce_new_transaction))
        self.assertIn("notify_order_placed", inspect.getsource(public_website_service.create_public_transaction))

    def test_a_failing_notification_cannot_undo_a_placed_order(self):
        """The caller restores the cart to active on any exception. If a notification
        raised, the customer got a live cart for an order that already existed and a
        retry placed it twice."""
        import inspect

        from app.services import customer_portal_service

        builder = inspect.getsource(customer_portal_service._build_transaction_from_items)
        announce_call = builder[builder.index("_announce_new_transaction"):]
        self.assertIn("except Exception", announce_call)

    def test_payment_confirmation_hangs_off_the_one_settlement_path(self):
        """Gateway callback, Stripe webhook, owner-recorded payment and the cashier till
        all recompute status through this function."""
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service._sync_transaction_payment_status)
        self.assertIn("notify_payment_confirmed", source)

    def test_the_confirmation_only_fires_when_the_status_actually_changed(self):
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service._sync_transaction_payment_status)
        self.assertIn('payment_status != transaction.get("paymentStatus")', source)


if __name__ == "__main__":
    unittest.main()


class OtpBodyRedactionTests(unittest.TestCase):
    """An OTP body contains the code, which defeats storing only a hash. The WhatsApp
    bridge reads messageText off the log row to actually send it, so a queued row has to
    keep the text until delivery is acknowledged - and lose it immediately after."""

    def test_a_queued_bridge_row_keeps_the_text_until_it_is_sent(self):
        import inspect

        from app.integrations.whatsapp import provider

        source = inspect.getsource(provider)
        self.assertIn('normalized_provider != "baileys"', source)

    def test_the_code_is_removed_once_delivery_is_acknowledged(self):
        import inspect

        from app.services import whatsapp_outbound_service

        source = inspect.getsource(whatsapp_outbound_service.acknowledge_outbound_message)
        self.assertIn("OTP_REDACTED_TEXT", source)
        self.assertIn('"otp"', source)

    def test_the_sms_channel_redacts_before_storing(self):
        """Nothing ever collects an SMS log row, so there is no reason to keep the code
        in it even briefly."""
        from app.integrations.sms.provider import _redact_if_otp

        self.assertEqual(_redact_if_otp("Your code is 123456", {"source": "otp"}), "[OTP code redacted]")
        self.assertEqual(_redact_if_otp("Your order shipped", {"source": "order"}), "Your order shipped")
