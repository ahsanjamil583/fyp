"""The concrete providers, and the registry that resolves one by code.

Four providers, one contract:

======================  ========  =====================================================
Provider                Flow      What ``initiate`` produces
======================  ========  =====================================================
JazzCash                redirect  a signed redirect to the gateway, or to the simulator
Easypaisa               redirect  the same, through Easypay
JazzCash / Easypaisa    otp       an emailed code, when the gateway runs in mock_otp mode
  in ``mock_otp`` mode
Stripe                  redirect  a Checkout session URL
======================  ========  =====================================================

A wallet's flow is decided by its configured mode, which is why ``get_provider`` looks
the mode up rather than taking it from the caller: a request cannot ask to be handled by
the mock. Switching a business to a real gateway is a change to ``.env`` and nothing
else - no code, no data migration, no change to the web client.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.payments import easypaisa, gateways, jazzcash, mock_otp
from app.integrations.payments.provider_base import (
    FLOW_OTP,
    FLOW_REDIRECT,
    BasePaymentProvider,
    ChallengeInstruction,
    ConfirmResult,
    InitiateResult,
    PaymentContext,
    PaymentProviderError,
    RedirectInstruction,
)

WALLET_PROVIDERS = ("jazzcash", "easypaisa")


class WalletRedirectProvider(BasePaymentProvider):
    """JazzCash or Easypaisa in simulator, sandbox or live mode.

    A thin adapter over ``gateways``, which already knows how to sign a request and how
    to check a callback. Nothing about the existing redirect behaviour changes here.
    """

    flow = FLOW_REDIRECT

    def __init__(self, code: str) -> None:
        self.code = code
        self.label = gateways.gateway_label(code)

    def mode(self) -> str:
        return gateways.gateway_mode(self.code)

    def is_available(self) -> bool:
        if self.mode() == "simulator":
            # Fine for testing, never something to route a real customer into.
            return settings.app_env != "production"
        return True

    def descriptor(self) -> dict[str, Any]:
        return {
            **super().descriptor(),
            "description": (
                f"Pay with {self.label}. You will be taken to a secure payment page and "
                "returned here once the payment is complete."
            ),
            "requiresOwnerApproval": False,
            "isOnline": True,
        }

    async def initiate(self, context: PaymentContext) -> InitiateResult:
        try:
            checkout = gateways.build_checkout(
                self.code,
                txn_ref=context.reference,
                amount=context.amount,
                return_url=context.return_url,
                bill_reference=context.order_number or context.reference,
                description=f"Payment for {context.order_number or 'order'}",
                customer_mobile=context.customer_mobile,
                customer_email=context.customer_email,
            )
        except (gateways.PaymentGatewayError, ValueError) as exc:
            raise PaymentProviderError(f"Unable to start {self.label} payment.") from exc

        return InitiateResult(
            flow=FLOW_REDIRECT,
            reference=context.reference,
            simulated=bool(checkout.get("simulated")),
            redirect=RedirectInstruction(
                url=checkout["url"],
                method=checkout.get("method", "GET"),
                fields=checkout.get("fields") or {},
            ),
            provider_session_id=context.reference,
            notes=f"{self.label} checkout started.",
        )

    async def confirm(self, context: PaymentContext, proof: dict[str, Any]) -> ConfirmResult:
        result = gateways.verify_callback(self.code, proof)
        return ConfirmResult(
            paid=bool(result.get("paid")),
            amount=float(result.get("amount") or 0),
            provider_transaction_id=str(result.get("providerTransactionId") or ""),
            response_code=str(result.get("responseCode") or ""),
            response_message=str(result.get("responseMessage") or ""),
            signature_valid=bool(result.get("signatureValid")),
        )


class WalletMockOtpProvider(BasePaymentProvider):
    """JazzCash or Easypaisa standing in as an emailed one-time code.

    Nothing is redirected and no money moves. The customer supplies a mobile number
    (recorded for the receipt, and deliberately not used for any decision - in a real
    wallet it identifies the payer's account, here it identifies nothing), a fresh
    random code goes to the address on their account, and the right code settles the
    order.

    The code is generated here and handed back once, in ``ChallengeInstruction.secret``,
    for the caller to hash and send. It is never stored or returned in plaintext.
    """

    flow = FLOW_OTP

    def __init__(self, code: str) -> None:
        self.code = code
        self.label = gateways.gateway_label(code)

    def mode(self) -> str:
        return "mock_otp"

    def is_available(self) -> bool:
        # The settings validator already refuses this mode in production; this is the
        # second line of the same defence, in case that check is ever relaxed.
        return settings.app_env != "production"

    def descriptor(self) -> dict[str, Any]:
        return {
            **super().descriptor(),
            "description": (
                f"Pay with {self.label}. Enter your mobile number and we will email you a "
                "verification code to confirm the payment."
            ),
            "requiresOwnerApproval": False,
            "isOnline": True,
            "requiresCustomerEmail": True,
            "demoNotice": "Simulated payment for demonstration. No real money is transferred.",
        }

    async def initiate(self, context: PaymentContext) -> InitiateResult:
        if not context.customer_email:
            raise PaymentProviderError("Please add an email to your profile to pay this way.")

        code = mock_otp.generate_payment_otp_code()
        return InitiateResult(
            flow=FLOW_OTP,
            reference=context.reference,
            simulated=True,
            challenge=ChallengeInstruction(
                kind="email_otp",
                sent_to=mock_otp.mask_email(context.customer_email),
                code_length=mock_otp.PAYMENT_OTP_CODE_LENGTH,
                expires_in_seconds=settings.payment_otp_expire_minutes * 60,
                max_attempts=settings.payment_otp_max_attempts,
                resend_cooldown_seconds=settings.payment_otp_resend_cooldown_seconds,
                secret=code,
                delivery_hint=f"We emailed a {mock_otp.PAYMENT_OTP_CODE_LENGTH}-digit code to {mock_otp.mask_email(context.customer_email)}.",
            ),
            provider_session_id=context.reference,
            notes=f"{self.label} demo payment started. A verification code was emailed.",
        )

    async def confirm(self, context: PaymentContext, proof: dict[str, Any]) -> ConfirmResult:
        """Check a submitted code against the stored hash.

        Expiry, attempt counting and locking belong to the caller, which owns the
        challenge row. This answers only "is this the right code".
        """
        submitted = mock_otp.normalize_payment_otp_code(proof.get("code"))
        expected_hash = str(proof.get("codeHash") or "")
        payment_record_id = str(proof.get("paymentRecordId") or "")
        if not submitted or not expected_hash or not payment_record_id:
            return ConfirmResult(paid=False, response_code="missing_code", response_message="No code was supplied.")

        if not mock_otp.verify_payment_otp_code(payment_record_id, submitted, self.code, expected_hash):
            return ConfirmResult(paid=False, response_code="invalid_code", response_message="The code did not match.")

        return ConfirmResult(
            paid=True,
            amount=context.amount,
            provider_transaction_id=mock_otp.build_mock_transaction_id(context.reference),
            response_code="000",
            response_message=f"{self.label} demo payment verified.",
        )


class StripeProvider(BasePaymentProvider):
    """Stripe Checkout, behind the same contract as the wallets.

    ``initiate`` creates the Checkout session; the redirect is its hosted URL. Stripe
    reports the outcome twice - on the return URL and again by webhook - and both paths
    land in ``payment_service``'s Stripe-specific reconciliation rather than in
    ``confirm``, because they carry a session object rather than a signed callback.
    ``confirm`` here covers the case the protocol defines: given a session, was it paid.
    """

    code = "stripe"
    label = "Stripe (card)"
    flow = FLOW_REDIRECT

    def mode(self) -> str:
        if not settings.stripe_secret_key:
            return "unconfigured"
        return "test" if str(settings.stripe_secret_key).startswith("sk_test") else "live"

    def is_available(self) -> bool:
        return bool(settings.stripe_secret_key)

    def descriptor(self) -> dict[str, Any]:
        return {
            **super().descriptor(),
            "description": (
                "Pay online by card through Stripe Checkout. You will be returned here once "
                "the payment is complete."
            ),
            "requiresOwnerApproval": False,
            "isOnline": True,
            "testCard": "4242 4242 4242 4242" if self.mode() == "test" else "",
        }

    async def initiate(self, context: PaymentContext) -> InitiateResult:
        if not settings.stripe_secret_key:
            raise PaymentProviderError("Stripe is not configured. Add STRIPE_SECRET_KEY to .env.")

        payload = {
            "mode": "payment",
            "success_url": context.success_url,
            "cancel_url": context.cancel_url,
            "client_reference_id": context.order_id,
            "customer_email": context.customer_email,
            "metadata[tenantId]": context.tenant_id,
            "metadata[transactionId]": context.order_id,
            "metadata[paymentRecordId]": context.reference,
            "payment_intent_data[metadata][tenantId]": context.tenant_id,
            "payment_intent_data[metadata][transactionId]": context.order_id,
            "payment_intent_data[metadata][paymentRecordId]": context.reference,
            # The order's currency, carried on the context, not whatever STRIPE_CURRENCY
            # happens to be. Hardcoding the setting charged a tenant trading in one
            # currency as if they traded in another.
            "line_items[0][price_data][currency]": (context.currency or settings.stripe_currency).lower(),
            "line_items[0][price_data][product_data][name]": f"{context.order_number or 'BizXusAI order'} payment",
            "line_items[0][price_data][unit_amount]": str(max(1, int(round(context.amount * 100)))),
            "line_items[0][quantity]": "1",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    "https://api.stripe.com/v1/checkout/sessions",
                    data=payload,
                    auth=(settings.stripe_secret_key, ""),
                    headers={"Idempotency-Key": f"bizxusai-checkout-{context.reference}"},
                )
        except httpx.HTTPError as exc:
            raise PaymentProviderError("Unable to create Stripe checkout session. Please try again.") from exc

        if response.status_code >= 400:
            try:
                message = response.json().get("error", {}).get("message")
            except Exception:
                message = ""
            raise PaymentProviderError(message or "Unable to create Stripe checkout session.")

        session = response.json()
        return InitiateResult(
            flow=FLOW_REDIRECT,
            reference=context.reference,
            simulated=False,
            redirect=RedirectInstruction(url=session.get("url", ""), method="GET"),
            provider_session_id=session.get("id", ""),
            provider_session_url=session.get("url", ""),
            notes="Stripe Checkout session is waiting for customer payment.",
        )

    async def confirm(self, context: PaymentContext, proof: dict[str, Any]) -> ConfirmResult:
        session = proof.get("session") or {}
        paid = str(session.get("payment_status") or "").lower() == "paid"
        amount_total = session.get("amount_total")
        amount = float(amount_total) / 100 if amount_total is not None else context.amount
        return ConfirmResult(
            paid=paid,
            amount=amount,
            provider_transaction_id=str(session.get("payment_intent") or session.get("id") or ""),
            response_code=str(session.get("payment_status") or ""),
            response_message="Stripe reported the session as paid." if paid else "Stripe has not marked this session paid.",
            signature_valid=True,
        )


def get_provider(code: str):
    """Resolve a provider by its payment-method code.

    For a wallet, the configured mode decides whether the redirect or the OTP
    implementation answers. A caller cannot select the mock: it is reached only by
    configuring that mode.
    """
    normalized = str(code or "").strip().lower()
    if normalized in {"stripe", "stripe_test"}:
        return StripeProvider()
    if normalized in WALLET_PROVIDERS:
        if gateways.gateway_mode(normalized) == "mock_otp":
            return WalletMockOtpProvider(normalized)
        return WalletRedirectProvider(normalized)
    raise PaymentProviderError(f"Unknown payment provider '{code}'.")


def provider_flow(code: str) -> str:
    """The flow a method uses, or an empty string when it is not a provider at all."""
    try:
        return get_provider(code).flow
    except PaymentProviderError:
        return ""


def is_otp_provider(code: str) -> bool:
    return provider_flow(code) == FLOW_OTP


def list_provider_descriptors() -> list[dict[str, Any]]:
    """Every provider the platform knows about, for diagnostics and readiness checks."""
    descriptors = [get_provider(wallet).descriptor() for wallet in WALLET_PROVIDERS]
    descriptors.append(StripeProvider().descriptor())
    return descriptors


def gateway_expiry_window() -> str:
    """Easypay wants an explicit expiry on each request."""
    return (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y%m%d %H%M%S")


__all__ = [
    "WALLET_PROVIDERS",
    "StripeProvider",
    "WalletMockOtpProvider",
    "WalletRedirectProvider",
    "easypaisa",
    "gateway_expiry_window",
    "get_provider",
    "is_otp_provider",
    "jazzcash",
    "list_provider_descriptors",
    "provider_flow",
]
