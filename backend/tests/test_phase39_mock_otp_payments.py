"""Phase 39: mock OTP wallet payments and the generalised provider protocol.

The things that would be expensive to get wrong: a code that is guessable, a code that
verifies against the wrong payment, a demo mode that leaks into production, and a
customer who is offered a payment method their account cannot complete.
"""

import unittest
from unittest.mock import patch

from bson import ObjectId
from fastapi import HTTPException

from app.core.config import GATEWAY_MODES, MOCK_GATEWAY_MODES, Settings
from app.integrations.payments import mock_otp, providers
from app.integrations.payments.provider_base import (
    FLOW_OTP,
    FLOW_REDIRECT,
    ChallengeInstruction,
    ConfirmResult,
    InitiateResult,
    PaymentContext,
    PaymentProviderError,
    RedirectInstruction,
)


def context(**overrides) -> PaymentContext:
    base = {
        "provider": "jazzcash",
        "reference": "64b7f0c2e1a4d8b9c0a1b2c3",
        "amount": 4500.0,
        "currency": "PKR",
        "order_id": "64b7f0c2e1a4d8b9c0a1b2c4",
        "order_number": "ORD-20260915-00001",
        "tenant_id": "64b7f0c2e1a4d8b9c0a1b2c5",
        "business_name": "Demo Store",
        "customer_email": "buyer@example.com",
        "customer_mobile": "03001234567",
    }
    base.update(overrides)
    return PaymentContext(**base)


class CodeGenerationTests(unittest.TestCase):
    def test_a_code_is_six_digits_and_zero_padded(self):
        for _ in range(200):
            code = mock_otp.generate_payment_otp_code()
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())

    def test_codes_are_not_predictable(self):
        codes = {mock_otp.generate_payment_otp_code() for _ in range(200)}
        # A stubbed or constant generator collapses this set to a handful of values.
        self.assertGreater(len(codes), 150)

    def test_demo_mode_never_produces_the_hard_coded_auth_code(self):
        """The regression this module exists to prevent.

        ``otp_service.generate_otp_code`` returns OTP_DEMO_CODE under demo mode. A payment
        settled by a code everyone already knows is not a payment system, so the payment
        generator must ignore those settings entirely.
        """
        from app.core import config as config_module

        demo_settings = Settings(
            jwt_secret_key="x" * 48,
            otp_demo_mode=True,
            otp_demo_code="123456",
        )
        with patch.object(config_module, "settings", demo_settings), patch.object(mock_otp, "settings", demo_settings):
            codes = {mock_otp.generate_payment_otp_code() for _ in range(200)}
        self.assertNotEqual(codes, {"123456"})
        self.assertGreater(len(codes), 150)

    def test_submitted_codes_are_read_through_spaces_and_dashes(self):
        self.assertEqual(mock_otp.normalize_payment_otp_code("483 920"), "483920")
        self.assertEqual(mock_otp.normalize_payment_otp_code("483-920"), "483920")
        self.assertEqual(mock_otp.normalize_payment_otp_code(None), "")


class CodeHashingTests(unittest.TestCase):
    RECORD = "64b7f0c2e1a4d8b9c0a1b2c3"
    OTHER = "64b7f0c2e1a4d8b9c0a1b2ff"

    def test_a_correct_code_verifies(self):
        digest = mock_otp.hash_payment_otp_code(self.RECORD, "483920", "jazzcash")
        self.assertTrue(mock_otp.verify_payment_otp_code(self.RECORD, "483920", "jazzcash", digest))

    def test_a_wrong_code_does_not_verify(self):
        digest = mock_otp.hash_payment_otp_code(self.RECORD, "483920", "jazzcash")
        self.assertFalse(mock_otp.verify_payment_otp_code(self.RECORD, "483921", "jazzcash", digest))

    def test_a_code_minted_for_one_payment_cannot_settle_another(self):
        digest = mock_otp.hash_payment_otp_code(self.RECORD, "483920", "jazzcash")
        self.assertFalse(mock_otp.verify_payment_otp_code(self.OTHER, "483920", "jazzcash", digest))

    def test_a_code_minted_for_one_wallet_cannot_settle_another(self):
        digest = mock_otp.hash_payment_otp_code(self.RECORD, "483920", "jazzcash")
        self.assertFalse(mock_otp.verify_payment_otp_code(self.RECORD, "483920", "easypaisa", digest))

    def test_an_empty_stored_hash_never_verifies(self):
        self.assertFalse(mock_otp.verify_payment_otp_code(self.RECORD, "483920", "jazzcash", ""))
        self.assertFalse(mock_otp.verify_payment_otp_code(self.RECORD, "483920", "jazzcash", None))

    def test_the_plaintext_code_is_not_recoverable_from_the_hash(self):
        digest = mock_otp.hash_payment_otp_code(self.RECORD, "483920", "jazzcash")
        self.assertNotIn("483920", digest)
        self.assertEqual(len(digest), 64)


class MaskingTests(unittest.TestCase):
    def test_an_email_is_recognisable_but_not_readable(self):
        masked = mock_otp.mask_email("asiya.rehman997@gmail.com")
        self.assertTrue(masked.endswith("@gmail.com"))
        self.assertNotIn("rehman997", masked)

    def test_a_short_local_part_is_still_masked(self):
        self.assertEqual(mock_otp.mask_email("ab@x.com"), "a***@x.com")

    def test_a_non_address_masks_to_stars(self):
        self.assertEqual(mock_otp.mask_email("not-an-email"), "****")

    def test_a_mobile_keeps_only_its_ends(self):
        self.assertEqual(mock_otp.mask_mobile("03001234567"), "0300****567")


class ProviderResolutionTests(unittest.TestCase):
    def test_a_wallet_in_simulator_mode_uses_the_redirect_flow(self):
        with patch.object(providers.gateways, "gateway_mode", return_value="simulator"):
            self.assertEqual(providers.get_provider("jazzcash").flow, FLOW_REDIRECT)

    def test_a_wallet_in_mock_otp_mode_uses_the_code_flow(self):
        with patch.object(providers.gateways, "gateway_mode", return_value="mock_otp"):
            provider = providers.get_provider("easypaisa")
            self.assertEqual(provider.flow, FLOW_OTP)
            self.assertEqual(provider.label, "Easypaisa")

    def test_a_wallet_in_live_mode_uses_the_redirect_flow(self):
        with patch.object(providers.gateways, "gateway_mode", return_value="live"):
            self.assertEqual(providers.get_provider("jazzcash").flow, FLOW_REDIRECT)

    def test_stripe_is_reachable_through_both_of_its_method_codes(self):
        self.assertIsInstance(providers.get_provider("stripe"), providers.StripeProvider)
        self.assertIsInstance(providers.get_provider("stripe_test"), providers.StripeProvider)

    def test_stripe_uses_the_redirect_flow_like_the_wallets(self):
        self.assertEqual(providers.StripeProvider().flow, FLOW_REDIRECT)

    def test_an_unknown_provider_is_refused(self):
        with self.assertRaises(PaymentProviderError):
            providers.get_provider("bitcoin")

    def test_provider_flow_is_blank_rather_than_raising_for_a_non_provider(self):
        self.assertEqual(providers.provider_flow("cod"), "")
        self.assertFalse(providers.is_otp_provider("manual_bank"))

    def test_every_provider_describes_itself_with_the_same_keys(self):
        required = {"provider", "label", "flow", "mode", "available", "simulated"}
        for descriptor in providers.list_provider_descriptors():
            self.assertTrue(required.issubset(descriptor), descriptor)


class MockOtpProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = providers.WalletMockOtpProvider("jazzcash")

    async def test_initiate_returns_a_challenge_and_no_redirect(self):
        result = await self.provider.initiate(context())
        self.assertEqual(result.flow, FLOW_OTP)
        self.assertIsNone(result.redirect)
        self.assertIsNotNone(result.challenge)
        self.assertTrue(result.simulated)

    async def test_initiate_produces_a_fresh_code_each_time(self):
        first = await self.provider.initiate(context())
        second = await self.provider.initiate(context())
        self.assertNotEqual(first.challenge.secret, second.challenge.secret)

    async def test_the_destination_is_masked_in_the_challenge(self):
        result = await self.provider.initiate(context(customer_email="buyer@example.com"))
        self.assertNotIn("buyer@example.com", result.challenge.sent_to)
        self.assertTrue(result.challenge.sent_to.endswith("@example.com"))

    async def test_a_customer_without_an_email_is_refused_with_the_agreed_wording(self):
        with self.assertRaises(PaymentProviderError) as ctx:
            await self.provider.initiate(context(customer_email=""))
        self.assertEqual(str(ctx.exception), "Please add an email to your profile to pay this way.")

    async def test_confirm_accepts_the_matching_code(self):
        initiation = await self.provider.initiate(context())
        code = initiation.challenge.secret
        digest = mock_otp.hash_payment_otp_code(context().reference, code, "jazzcash")
        result = await self.provider.confirm(
            context(), {"code": code, "codeHash": digest, "paymentRecordId": context().reference}
        )
        self.assertTrue(result.paid)
        self.assertEqual(result.amount, 4500.0)
        self.assertTrue(result.provider_transaction_id.startswith("MOCKOTP"))

    async def test_confirm_refuses_a_wrong_code(self):
        digest = mock_otp.hash_payment_otp_code(context().reference, "111111", "jazzcash")
        result = await self.provider.confirm(
            context(), {"code": "222222", "codeHash": digest, "paymentRecordId": context().reference}
        )
        self.assertFalse(result.paid)
        self.assertEqual(result.response_code, "invalid_code")

    async def test_confirm_refuses_an_empty_submission(self):
        result = await self.provider.confirm(context(), {"code": "", "codeHash": "abc", "paymentRecordId": "x"})
        self.assertFalse(result.paid)
        self.assertEqual(result.response_code, "missing_code")

    async def test_confirm_settles_the_amount_the_server_computed(self):
        """A provider never invents an amount; it echoes the one it was given."""
        initiation = await self.provider.initiate(context(amount=999.5))
        digest = mock_otp.hash_payment_otp_code(context().reference, initiation.challenge.secret, "jazzcash")
        result = await self.provider.confirm(
            context(amount=999.5),
            {"code": initiation.challenge.secret, "codeHash": digest, "paymentRecordId": context().reference},
        )
        self.assertEqual(result.amount, 999.5)


class InitiateResultExposureTests(unittest.TestCase):
    def test_the_public_payload_never_carries_the_code(self):
        result = InitiateResult(
            flow=FLOW_OTP,
            reference="abc",
            challenge=ChallengeInstruction(
                kind="email_otp",
                sent_to="bu***r@example.com",
                code_length=6,
                expires_in_seconds=300,
                max_attempts=3,
                resend_cooldown_seconds=60,
                secret="483920",
            ),
        )
        payload = result.public_dict()
        self.assertNotIn("483920", repr(payload))
        self.assertNotIn("secret", payload["challenge"])
        self.assertEqual(payload["challenge"]["sentTo"], "bu***r@example.com")

    def test_a_redirect_result_carries_its_fields(self):
        result = InitiateResult(
            flow=FLOW_REDIRECT,
            reference="abc",
            redirect=RedirectInstruction(url="https://gateway.example/pay", method="POST", fields={"a": "1"}),
        )
        payload = result.public_dict()
        self.assertEqual(payload["redirect"]["method"], "POST")
        self.assertEqual(payload["redirect"]["fields"], {"a": "1"})
        self.assertNotIn("challenge", payload)


class GatewayModeTests(unittest.TestCase):
    def test_mock_otp_is_a_recognised_mode(self):
        self.assertIn("mock_otp", GATEWAY_MODES)
        self.assertIn("mock_otp", MOCK_GATEWAY_MODES)

    def test_an_unknown_mode_falls_back_to_the_simulator(self):
        self.assertEqual(Settings(jwt_secret_key="x" * 48, jazzcash_mode="nonsense").jazzcash_mode, "simulator")

    def test_mock_otp_survives_the_credential_fallback(self):
        """Unlike sandbox/live, the mock needs no credentials, so it must not be downgraded."""
        configured = Settings(jwt_secret_key="x" * 48, jazzcash_mode="mock_otp")
        self.assertEqual(configured.effective_jazzcash_mode, "mock_otp")

    def test_production_refuses_to_start_with_a_mock_wallet(self):
        with self.assertRaises(ValueError) as ctx:
            Settings(
                app_env="production",
                debug=False,
                jwt_secret_key="x" * 48,
                bcrypt_rounds=12,
                jazzcash_mode="mock_otp",
            )
        self.assertIn("mock_otp", str(ctx.exception))

    def test_a_mock_wallet_is_unavailable_in_production_even_if_configuration_slipped_through(self):
        # Modes are pinned so the test does not inherit the developer's .env - which,
        # with mock_otp set, the production validator would rightly refuse to build.
        production = Settings(
            jwt_secret_key="x" * 48,
            app_env="production",
            debug=False,
            bcrypt_rounds=12,
            jazzcash_mode="live",
            easypaisa_mode="live",
            jazzcash_merchant_id="m",
            jazzcash_password="p",
            jazzcash_integrity_salt="s",
            easypaisa_store_id="s",
            easypaisa_hash_key="0123456789abcdef",
        )
        with patch.object(providers, "settings", production):
            self.assertFalse(providers.WalletMockOtpProvider("jazzcash").is_available())


class MethodCatalogueTests(unittest.TestCase):
    """Who is offered what, which is decision 1 and 2 of the brief."""

    def _settings_doc(self):
        from app.services.payment_service import _default_settings

        doc = _default_settings(ObjectId())
        doc["jazzCashEnabled"] = True
        doc["easyPaisaEnabled"] = True
        return doc

    def test_a_signed_in_customer_is_offered_the_code_flow(self):
        from app.services.payment_service import serialize_customer_payment_options

        with patch.object(providers.gateways, "gateway_mode", return_value="mock_otp"):
            options = serialize_customer_payment_options(self._settings_doc(), allow_otp=True)
        codes = {method["code"]: method.get("flow") for method in options["methods"]}
        self.assertEqual(codes.get("jazzcash"), FLOW_OTP)
        self.assertEqual(codes.get("easypaisa"), FLOW_OTP)

    def test_a_guest_is_offered_the_manual_wallet_instead(self):
        from app.services.payment_service import serialize_customer_payment_options

        with patch.object(providers.gateways, "gateway_mode", return_value="mock_otp"):
            options = serialize_customer_payment_options(self._settings_doc(), allow_otp=False)
        codes = {method["code"] for method in options["methods"]}
        self.assertIn("jazzcash_mock", codes)
        self.assertIn("easypaisa_mock", codes)
        # A guest has no account to email, so the code flow must not be advertised.
        self.assertNotIn("jazzcash", codes)
        self.assertNotIn("easypaisa", codes)

    def test_cash_and_bank_transfer_stay_available_to_guests(self):
        from app.services.payment_service import serialize_customer_payment_options

        with patch.object(providers.gateways, "gateway_mode", return_value="mock_otp"):
            options = serialize_customer_payment_options(self._settings_doc(), allow_otp=False)
        codes = {method["code"] for method in options["methods"]}
        self.assertIn("cod", codes)
        self.assertIn("manual_bank", codes)

    def test_the_code_flow_declares_that_it_needs_an_email(self):
        from app.services.payment_service import serialize_customer_payment_options

        with patch.object(providers.gateways, "gateway_mode", return_value="mock_otp"):
            options = serialize_customer_payment_options(self._settings_doc(), allow_otp=True)
        wallet = next(method for method in options["methods"] if method["code"] == "jazzcash")
        self.assertTrue(wallet["requiresCustomerEmail"])
        self.assertIn("No real money", wallet["demoNotice"])


class RequestContractTests(unittest.TestCase):
    def test_the_checkout_request_cannot_carry_an_amount(self):
        """The amount is the order's, always. There is no field to override it with."""
        from app.schemas.payment_schema import WalletOtpCheckoutRequest

        self.assertNotIn("amount", WalletOtpCheckoutRequest.model_fields)
        parsed = WalletOtpCheckoutRequest(provider="jazzcash", mobileNumber="03001234567", amount=1)
        self.assertFalse(hasattr(parsed, "amount"))

    def test_a_missing_mobile_number_is_rejected(self):
        from pydantic import ValidationError

        from app.schemas.payment_schema import WalletOtpCheckoutRequest

        with self.assertRaises(ValidationError):
            WalletOtpCheckoutRequest(provider="jazzcash", mobileNumber="")


class EmailContentTests(unittest.TestCase):
    def test_the_email_states_the_order_amount_and_that_it_is_simulated(self):
        from app.services.email_service import build_payment_otp_email_body

        body = build_payment_otp_email_body(
            "483920",
            amount=4500.0,
            currency="PKR",
            business_name="Demo Store",
            order_number="ORD-1",
            provider_label="JazzCash",
        )
        self.assertIn("483920", body)
        self.assertIn("PKR 4,500.00", body)
        self.assertIn("ORD-1", body)
        self.assertIn("simulated", body.lower())

    def test_the_payment_email_has_no_demo_short_circuit(self):
        """``send_otp_email`` returns without sending under OTP_DEMO_MODE.

        The payment sender must not, or the customer at the checkout never receives the
        code they are being asked to type in.
        """
        import inspect

        from app.services import email_service

        source = inspect.getsource(email_service.send_payment_otp_email)
        self.assertNotIn("should_use_email_demo_delivery", source)


class ConfirmResultTests(unittest.TestCase):
    def test_an_unpaid_result_defaults_to_a_zero_amount(self):
        result = ConfirmResult(paid=False)
        self.assertEqual(result.amount, 0.0)
        self.assertTrue(result.signature_valid)


class ProtocolRoutingTests(unittest.TestCase):
    """Every payment starts through ``initiate``, not through a provider-specific call.

    This is what makes "add a provider" mean "write a provider". If someone reintroduces
    a direct ``gateways.build_checkout`` or an inline Stripe POST in the service layer,
    these fail.
    """

    def _source(self, function):
        import inspect

        return inspect.getsource(function)

    def test_wallet_checkout_goes_through_the_protocol(self):
        from app.services.payment_service import create_gateway_checkout

        source = self._source(create_gateway_checkout)
        self.assertIn("await gateway.initiate(context)", source)
        self.assertNotIn("gateways.build_checkout(", source)

    def test_stripe_checkout_goes_through_the_protocol(self):
        from app.services.payment_service import create_customer_stripe_checkout_session

        source = self._source(create_customer_stripe_checkout_session)
        self.assertIn("await stripe_provider.initiate(context)", source)
        self.assertNotIn("api.stripe.com", source)

    def test_the_otp_flow_goes_through_the_protocol(self):
        from app.services.payment_service import start_wallet_otp_payment

        self.assertIn("await provider.initiate(context)", self._source(start_wallet_otp_payment))

    def test_a_code_flow_wallet_is_refused_by_the_redirect_route(self):
        from app.services.payment_service import create_gateway_checkout

        source = self._source(create_gateway_checkout)
        self.assertIn("FLOW_OTP", source)
        self.assertIn("verification-code payments", source)

    def test_availability_has_one_answer(self):
        from app.services.payment_service import _gateway_available

        self.assertIn("providers.get_provider(provider).is_available()", self._source(_gateway_available))


class MockCredentialFallbackTests(unittest.TestCase):
    """Both local modes must sign with the placeholder credentials.

    Regression: keying the fallback off `is_simulated` alone meant a server in mock_otp
    mode reached for an empty real key, so anything that signed a payload raised instead.
    """

    def test_simulator_mode_uses_the_placeholder_credentials(self):
        from app.integrations.payments import gateways

        with patch.object(gateways, "gateway_mode", return_value="simulator"):
            self.assertEqual(gateways.jazzcash_salt(), gateways.SIMULATOR_JAZZCASH_SALT)
            self.assertEqual(gateways.easypaisa_key(), gateways.SIMULATOR_EASYPAISA_KEY)

    def test_mock_otp_mode_uses_the_placeholder_credentials_too(self):
        from app.integrations.payments import gateways

        with patch.object(gateways, "gateway_mode", return_value="mock_otp"):
            self.assertEqual(gateways.jazzcash_salt(), gateways.SIMULATOR_JAZZCASH_SALT)
            self.assertEqual(gateways.easypaisa_key(), gateways.SIMULATOR_EASYPAISA_KEY)

    def test_a_real_mode_uses_the_configured_credentials(self):
        from app.integrations.payments import gateways

        with patch.object(gateways, "gateway_mode", return_value="live"):
            self.assertEqual(gateways.jazzcash_salt(), gateways.settings.jazzcash_integrity_salt)

    def test_a_simulated_callback_still_signs_in_mock_otp_mode(self):
        from app.integrations.payments import gateways

        with patch.object(gateways, "gateway_mode", return_value="mock_otp"):
            payload = gateways.build_simulated_callback("easypaisa", txn_ref="BZX1", amount=10.0, approve=True)
        self.assertTrue(payload["merchantHashedReq"])


if __name__ == "__main__":
    unittest.main()


class StripeSettlementGuardTests(unittest.TestCase):
    """What Stripe actually has to say before an order is treated as paid."""

    def test_only_payment_status_settles_an_order(self):
        from app.services.payment_service import stripe_session_is_paid

        self.assertTrue(stripe_session_is_paid({"payment_status": "paid"}))
        self.assertTrue(stripe_session_is_paid({"payment_status": "no_payment_required"}))

    def test_a_completed_but_unpaid_session_is_not_paid(self):
        """Stripe sends checkout.session.completed with payment_status "unpaid" for
        delayed-notification methods; the money may never arrive."""
        from app.services.payment_service import stripe_session_is_paid

        self.assertFalse(stripe_session_is_paid({"status": "complete", "payment_status": "unpaid"}))
        self.assertFalse(stripe_session_is_paid({"status": "complete"}))
        self.assertFalse(stripe_session_is_paid({}))
        self.assertFalse(stripe_session_is_paid(None))


class StripeCurrencyTests(unittest.TestCase):
    def test_the_order_currency_is_used(self):
        from unittest.mock import patch

        from app.services import payment_service

        with patch.object(payment_service.settings, "stripe_currency", "PKR"):
            self.assertEqual(payment_service._stripe_currency_for({"pricing": {"currency": "PKR"}}), "PKR")

    def test_a_mismatch_is_refused_rather_than_charged_in_the_wrong_currency(self):
        """There are no exchange rates here, so there is no correct number to send."""
        from unittest.mock import patch

        from app.services import payment_service

        with patch.object(payment_service.settings, "stripe_currency", "PKR"):
            with self.assertRaises(HTTPException) as caught:
                payment_service._stripe_currency_for({"pricing": {"currency": "USD"}})
        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("USD", caught.exception.detail)
        self.assertIn("PKR", caught.exception.detail)

    def test_an_order_with_no_currency_falls_back_to_the_configured_one(self):
        from unittest.mock import patch

        from app.services import payment_service

        with patch.object(payment_service.settings, "stripe_currency", "PKR"):
            self.assertEqual(payment_service._stripe_currency_for({"pricing": {}}), "PKR")


class StripeWebhookClaimTests(unittest.TestCase):
    """The dedupe claim must not use upsert against a unique index.

    `eventId` is unique, so an upsert whose filter excludes the existing row makes Mongo
    attempt an insert and raise DuplicateKeyError instead of returning None. That turned
    every ordinary Stripe retry into a 500, and Stripe then retried forever.
    """

    def test_the_claim_does_not_upsert_past_the_unique_index(self):
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service.process_stripe_webhook)
        claim = source[source.index("find_one_and_update"):source.index("try:")]
        self.assertNotIn("upsert=True", claim, "upsert against a unique eventId raises instead of returning None")
        self.assertIn("DuplicateKeyError", source, "the insert race must be caught and reported as a duplicate")
        self.assertIn('"duplicate": True', source)

    def test_the_event_id_index_is_still_unique(self):
        """If this ever stops being unique the two-step claim above is no longer safe."""
        import inspect

        from app.db import indexes

        source = inspect.getsource(indexes.create_indexes)
        # Created through _ensure_index now, which raises rather than swallowing a
        # failed unique build. The property the claim depends on is unchanged.
        self.assertIn('_ensure_index(db.stripe_webhook_events, "eventId", unique=True)', source)


class GatewayCallbackBalanceCapTests(unittest.TestCase):
    def test_the_gateway_credit_is_capped_at_the_live_balance(self):
        """The OTP path re-read the balance before crediting; the gateway callback did
        not, so two attempts opened back to back could each settle the full total."""
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service.complete_gateway_payment)
        self.assertIn("_calculate_payment_summary", source)
        self.assertIn("min(reported_amount", source)

    def test_superseding_covers_the_whole_order_not_one_provider(self):
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service._supersede_pending_attempts)
        self.assertIn('"provider": {"$nin": ["", None]}', source)


class StripeSettlementProtectionsTests(unittest.TestCase):
    """The Stripe settle path was the only one of three that never received the claim,
    the balance cap or the supersede its JazzCash and Easypaisa twins have."""

    def test_the_settlement_is_a_compare_and_set(self):
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service.mark_stripe_checkout_completed)
        self.assertIn('"status": "pending_verification"', source)
        self.assertIn("claimed.modified_count", source)

    def test_the_settlement_is_capped_at_the_live_balance(self):
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service.mark_stripe_checkout_completed)
        self.assertIn("_calculate_payment_summary", source)
        self.assertIn("min(paid_amount", source)

    def test_both_stripe_creation_sites_supersede(self):
        import inspect

        from app.services import payment_service

        for name in ("create_customer_stripe_checkout_session", "create_public_stripe_checkout_session"):
            source = inspect.getsource(getattr(payment_service, name))
            self.assertIn("_supersede_pending_attempts", source, name)


class CodBucketTests(unittest.TestCase):
    def test_cod_records_are_retired_once_cash_arrives(self):
        """Nothing closed the COD placeholder when the money was collected, so the same
        order was counted in both the received and the COD totals."""
        import inspect

        from app.services import payment_service

        self.assertTrue(hasattr(payment_service, "close_cod_records_for_transaction"))
        # Wired into the one function every settlement path funnels through.
        sync = inspect.getsource(payment_service._sync_transaction_payment_status)
        self.assertIn("close_cod_records_for_transaction", sync)

    def test_the_importer_records_a_refund_amount(self):
        """The guard accepted `refunded` while the amount feeding it stayed 0, so the
        reconciling call was dead code."""
        import inspect

        from app.services import order_import_service

        source = inspect.getsource(order_import_service)
        self.assertIn('paid_amount = total if payment_status in {"paid", "cod", "refunded"}', source)
