"""JazzCash and Easypaisa redirect gateways.

The signature is the only thing separating a real gateway confirmation from anyone who
can POST to a public callback URL, so most of these tests are about what must NOT be
accepted as a payment.
"""

import unittest
from unittest.mock import patch

from app.integrations.payments import easypaisa, gateways, jazzcash


class JazzCashSigningTests(unittest.TestCase):
    SALT = "test_integrity_salt"

    def test_a_signed_payload_verifies(self):
        payload = {"pp_TxnRefNo": "BZX1", "pp_Amount": "420000", "pp_ResponseCode": "000"}
        payload["pp_SecureHash"] = jazzcash.secure_hash(payload, self.SALT)
        result = jazzcash.verify_callback(payload, self.SALT)
        self.assertTrue(result["signatureValid"])
        self.assertTrue(result["paid"])
        # JazzCash works in paisa; the record must hold rupees.
        self.assertEqual(result["amount"], 4200.0)

    def test_changing_the_amount_breaks_the_signature(self):
        payload = {"pp_TxnRefNo": "BZX1", "pp_Amount": "420000", "pp_ResponseCode": "000"}
        payload["pp_SecureHash"] = jazzcash.secure_hash(payload, self.SALT)
        payload["pp_Amount"] = "1"
        result = jazzcash.verify_callback(payload, self.SALT)
        self.assertFalse(result["signatureValid"])
        self.assertFalse(result["paid"])

    def test_an_unsigned_success_is_not_a_payment(self):
        result = jazzcash.verify_callback({"pp_TxnRefNo": "BZX1", "pp_Amount": "420000", "pp_ResponseCode": "000"}, self.SALT)
        self.assertFalse(result["signatureValid"])
        self.assertFalse(result["paid"])

    def test_a_signature_from_a_different_salt_is_rejected(self):
        payload = {"pp_TxnRefNo": "BZX1", "pp_Amount": "100", "pp_ResponseCode": "000"}
        payload["pp_SecureHash"] = jazzcash.secure_hash(payload, "someone_elses_salt")
        self.assertFalse(jazzcash.verify_callback(payload, self.SALT)["signatureValid"])

    def test_a_declined_response_is_signed_but_not_paid(self):
        payload = {"pp_TxnRefNo": "BZX1", "pp_Amount": "100", "pp_ResponseCode": "124"}
        payload["pp_SecureHash"] = jazzcash.secure_hash(payload, self.SALT)
        result = jazzcash.verify_callback(payload, self.SALT)
        self.assertTrue(result["signatureValid"])
        self.assertFalse(result["paid"])

    def test_empty_fields_are_left_out_of_the_signature(self):
        # The gateway drops empty values before hashing; keeping them would make every
        # request fail with a signature error that reads like a credentials problem.
        with_empty = {"pp_TxnRefNo": "BZX1", "pp_BankID": "", "pp_SubMerchantID": ""}
        without_empty = {"pp_TxnRefNo": "BZX1"}
        self.assertEqual(jazzcash.secure_hash(with_empty, self.SALT), jazzcash.secure_hash(without_empty, self.SALT))

    def test_the_request_carries_the_amount_in_paisa(self):
        with patch.object(jazzcash.settings, "jazzcash_integrity_salt", self.SALT):
            request = jazzcash.build_checkout_request(
                txn_ref="BZX1", amount=4200.0, return_url="http://x/cb", bill_reference="ORD-1", description="d"
            )
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["fields"]["pp_Amount"], "420000")
        self.assertTrue(request["fields"]["pp_SecureHash"])


class EasypaisaSigningTests(unittest.TestCase):
    KEY = "TestHashKey12345"  # Easypay keys are exactly 16 characters.

    def test_a_signed_payload_verifies(self):
        payload = {"orderRefNum": "BZX1", "amount": "4200.00", "status": "0000"}
        payload["merchantHashedReq"] = easypaisa.encrypt_request(easypaisa._hashable_string(payload), self.KEY)
        result = easypaisa.verify_callback(payload, self.KEY)
        self.assertTrue(result["signatureValid"])
        self.assertTrue(result["paid"])
        self.assertEqual(result["amount"], 4200.0)

    def test_changing_the_amount_breaks_the_signature(self):
        payload = {"orderRefNum": "BZX1", "amount": "4200.00", "status": "0000"}
        payload["merchantHashedReq"] = easypaisa.encrypt_request(easypaisa._hashable_string(payload), self.KEY)
        payload["amount"] = "1.00"
        self.assertFalse(easypaisa.verify_callback(payload, self.KEY)["paid"])

    def test_an_unsigned_success_is_not_a_payment(self):
        result = easypaisa.verify_callback({"orderRefNum": "BZX1", "amount": "4200.00", "status": "0000"}, self.KEY)
        self.assertFalse(result["signatureValid"])
        self.assertFalse(result["paid"])

    def test_a_wrong_length_key_is_refused_rather_than_padded(self):
        with self.assertRaises(ValueError):
            easypaisa.encrypt_request("amount=1", "short")

    def test_encryption_is_stable_for_the_same_input(self):
        first = easypaisa.encrypt_request("amount=1&storeId=2", self.KEY)
        second = easypaisa.encrypt_request("amount=1&storeId=2", self.KEY)
        self.assertEqual(first, second)


class GatewayModeTests(unittest.TestCase):
    def test_sandbox_without_credentials_falls_back_to_the_simulator(self):
        # Sending a customer to a gateway that will reject the request is worse than
        # telling the developer the credentials are missing.
        with (
            patch.object(gateways.settings, "jazzcash_mode", "sandbox"),
            patch.object(gateways.settings, "jazzcash_merchant_id", ""),
            patch.object(gateways.settings, "jazzcash_password", ""),
            patch.object(gateways.settings, "jazzcash_integrity_salt", ""),
        ):
            self.assertEqual(gateways.gateway_mode("jazzcash"), "simulator")
            self.assertTrue(gateways.gateway_status("jazzcash")["fellBackToSimulator"])

    def test_configured_sandbox_targets_the_gateway(self):
        with (
            patch.object(gateways.settings, "jazzcash_mode", "sandbox"),
            patch.object(gateways.settings, "jazzcash_merchant_id", "MC1"),
            patch.object(gateways.settings, "jazzcash_password", "pw"),
            patch.object(gateways.settings, "jazzcash_integrity_salt", "salt"),
        ):
            checkout = gateways.build_checkout(
                "jazzcash", txn_ref="BZX1", amount=100, return_url="http://x/cb", bill_reference="O1", description="d"
            )
        self.assertIn("sandbox.jazzcash.com.pk", checkout["url"])
        self.assertFalse(checkout["simulated"])

    def test_an_unknown_gateway_is_rejected(self):
        with self.assertRaises(gateways.PaymentGatewayError):
            gateways.gateway_mode("paypal")

    def test_simulator_callbacks_go_through_the_real_verification(self):
        for provider in gateways.GATEWAY_PROVIDERS:
            payload = gateways.build_simulated_callback(provider, txn_ref="BZX1", amount=4200.0, approve=True)
            result = gateways.verify_callback(provider, payload)
            self.assertTrue(result["signatureValid"], provider)
            self.assertTrue(result["paid"], provider)
            self.assertEqual(result["amount"], 4200.0, provider)

    def test_a_simulated_cancellation_is_signed_but_unpaid(self):
        for provider in gateways.GATEWAY_PROVIDERS:
            payload = gateways.build_simulated_callback(provider, txn_ref="BZX1", amount=10.0, approve=False)
            result = gateways.verify_callback(provider, payload)
            self.assertTrue(result["signatureValid"], provider)
            self.assertFalse(result["paid"], provider)

    def test_a_placeholder_backend_url_does_not_reach_the_simulator(self):
        with patch.object(gateways.settings, "backend_public_url", "https://your-ngrok-or-deployed-backend.example.com"):
            self.assertIn("localhost", gateways._api_base_url())


class PaymentMethodCatalogTests(unittest.TestCase):
    def test_the_wallets_are_offered_as_redirect_methods(self):
        from app.services import payment_service

        doc = {"codEnabled": True, "jazzCashEnabled": True, "easyPaisaEnabled": True}
        with patch.object(payment_service.settings, "app_env", "development"):
            options = payment_service.serialize_customer_payment_options(doc)
        codes = [method["code"] for method in options["methods"]]
        self.assertIn("jazzcash", codes)
        self.assertIn("easypaisa", codes)
        for method in options["methods"]:
            if method["code"] in {"jazzcash", "easypaisa"}:
                self.assertTrue(method["isOnline"])
                self.assertFalse(method["requiresOwnerApproval"])

    def test_production_without_credentials_offers_the_manual_flow_instead(self):
        from app.services import payment_service

        doc = {"jazzCashEnabled": True, "easyPaisaEnabled": True}
        with (
            patch.object(payment_service.settings, "app_env", "production"),
            patch.object(gateways.settings, "jazzcash_mode", "simulator"),
            patch.object(gateways.settings, "easypaisa_mode", "simulator"),
        ):
            options = payment_service.serialize_customer_payment_options(doc)
        codes = [method["code"] for method in options["methods"]]
        self.assertIn("jazzcash_mock", codes)
        self.assertNotIn("jazzcash", codes)

    def test_a_gateway_reference_round_trips_to_its_payment_record(self):
        from app.services.payment_service import _build_gateway_txn_ref, _record_id_from_txn_ref

        record_id = "6aa2f4f3f95991f20d523f5e"
        self.assertEqual(_record_id_from_txn_ref(_build_gateway_txn_ref(record_id)), record_id)


class CustomerRouteScopeTests(unittest.TestCase):
    """Where the checkout route lives is part of its authentication.

    The web client picks the customer access token for URLs under "/customer/" and the
    business token for everything else. A customer-only endpoint outside that prefix is
    therefore called with the wrong token and answers 403, which is exactly what a
    checkout under "/payments/" did.
    """

    def _app_paths(self):
        from unittest.mock import AsyncMock, patch

        with (
            patch("app.main.connect_to_mongo", new=AsyncMock()),
            patch("app.main.close_mongo_connection", new=AsyncMock()),
            patch("app.main.create_indexes", new=AsyncMock()),
            patch("app.main.seed_default_admin", new=AsyncMock()),
            patch("app.main.seed_modules", new=AsyncMock()),
            patch("app.main.seed_business_categories", new=AsyncMock()),
        ):
            from app.main import create_app

            return [getattr(route, "path", "") for route in create_app().routes]

    def test_starting_a_gateway_checkout_is_under_the_customer_prefix(self):
        paths = self._app_paths()
        self.assertIn("/api/v1/customer/transactions/{orderId}/gateway-checkout", paths)

    def test_no_customer_authenticated_route_sits_outside_that_prefix(self):
        import app.api.v1.payment_gateway_routes as gateway_routes

        source = open(gateway_routes.__file__, encoding="utf-8").read()
        self.assertNotIn("get_current_customer_user", source)

    def test_the_gateway_callback_and_simulator_stay_public(self):
        paths = self._app_paths()
        self.assertIn("/api/v1/payments/{provider}/callback", paths)
        self.assertIn("/api/v1/payments/{provider}/simulator/{txnRef}", paths)


class StripeAvailabilityTests(unittest.TestCase):
    def test_stripe_is_hidden_without_a_secret_key(self):
        from app.services import payment_service

        with patch.object(payment_service.settings, "stripe_secret_key", ""):
            codes = [m["code"] for m in payment_service.serialize_customer_payment_options({"stripeEnabled": True})["methods"]]
        self.assertNotIn("stripe_test", codes)

    def test_stripe_is_offered_once_a_key_exists(self):
        from app.services import payment_service

        with patch.object(payment_service.settings, "stripe_secret_key", "sk_test_example"):
            codes = [m["code"] for m in payment_service.serialize_customer_payment_options({"stripeEnabled": True})["methods"]]
        self.assertIn("stripe_test", codes)


if __name__ == "__main__":
    unittest.main()


class CallbackTrustBoundaryTests(unittest.TestCase):
    """What a verified signature actually proves.

    A gateway signature is only worth what it covers. JazzCash signs the response code,
    so a verified JazzCash callback attests to the outcome. Easypay echoes back the hash
    it was given over the *request* fields, and the customer is handed that same hash in
    the redirect form, so it attests to nothing about whether money moved.
    """

    def test_jazzcash_signs_the_payment_outcome(self):
        payload = {"pp_TxnRefNo": "BZX1", "pp_Amount": "420000", "pp_ResponseCode": "000"}
        payload["pp_SecureHash"] = jazzcash.secure_hash(payload, "salt")
        self.assertTrue(jazzcash.verify_callback(payload, "salt")["outcomeSigned"])

    def test_easypaisa_does_not_sign_the_payment_outcome(self):
        """`status` is absent from HASHED_FIELDS, so the same valid hash verifies whether
        the response says paid or failed. The flag is what stops it settling an order."""
        key = "BizXusSimKey1234"
        signed_fields = {
            "amount": "4200.0",
            "autoRedirect": "1",
            "emailAddr": "buyer@example.com",
            "expiryDate": "20260101 000000",
            "mobileNum": "03001234567",
            "orderRefNum": "BZX1",
            "paymentMethod": "CC_PAYMENT_METHOD",
            "postBackURL": "https://example.test/callback",
            "storeId": "1234",
        }
        request_hash = easypaisa.encrypt_request(easypaisa._hashable_string(signed_fields), key)

        # Exactly what a customer can replay: the fields and hash they were given, plus a
        # success status they chose themselves.
        forged = {**signed_fields, "merchantHashedReq": request_hash, "status": "0000"}
        result = easypaisa.verify_callback(forged, key)

        self.assertTrue(result["signatureValid"], "the echoed request hash does verify")
        self.assertFalse(result["outcomeSigned"], "but it must not be treated as proof of payment")


class GatewayCallbackRecordBindingTests(unittest.TestCase):
    def test_a_callback_can_only_settle_its_own_provider_and_flow(self):
        """Matching on the record id alone let a JazzCash callback settle a Stripe, manual
        or OTP record, because every checkout hands the customer its own record id."""
        import inspect

        from app.services import payment_service

        source = inspect.getsource(payment_service.complete_gateway_payment)
        self.assertIn('"provider": provider', source)
        self.assertIn('"flow": FLOW_REDIRECT', source)
        self.assertIn("is_available()", source)
