"""One contract every payment provider implements.

Before this, each provider was wired into ``payment_service`` by hand: JazzCash and
Easypaisa through ``gateways.build_checkout``, Stripe through its own inline HTTP call,
and each with its own idea of what "start a payment" returned. Adding a provider meant
editing the service, the routes and the web client.

A provider now answers two questions:

* ``initiate(context)`` - what must happen next for this customer to pay?
* ``confirm(context, proof)`` - does this proof mean the money arrived?

and declares which *flow* it uses, because that is the only thing callers legitimately
need to branch on:

``redirect``
    The customer leaves for the provider's page and the provider reports back, by
    callback (JazzCash, Easypaisa) or by return URL plus webhook (Stripe).
``otp``
    The customer stays here. The provider issues a challenge and settles the payment
    when the right code comes back.

Everything else - signing, HTTP calls, code generation - stays inside the provider.
``payment_service`` owns the parts that are the same for every provider: reading the
amount from the order, writing the ``payment_records`` row, and recomputing the order's
payment status afterwards.

Providers here are stateless descriptions of a protocol. They never touch the database;
their caller does. That is what keeps them unit-testable without Mongo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

FLOW_REDIRECT = "redirect"
FLOW_OTP = "otp"
VALID_FLOWS = frozenset({FLOW_REDIRECT, FLOW_OTP})


class PaymentProviderError(Exception):
    """A provider could not act, with a message that is safe to show a customer."""


@dataclass(frozen=True)
class PaymentContext:
    """Everything a provider may know about the payment being started.

    Assembled by ``payment_service`` from the order in the database. ``amount`` is the
    order's outstanding balance as the server computed it - a provider never sees, and
    can never be handed, an amount that came from the client.
    """

    provider: str
    reference: str
    amount: float
    currency: str
    order_id: str
    order_number: str
    tenant_id: str
    business_name: str = ""
    customer_name: str = ""
    customer_email: str = ""
    customer_mobile: str = ""
    return_url: str = ""
    success_url: str = ""
    cancel_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RedirectInstruction:
    """Where to send the browser, and how."""

    url: str
    method: str = "GET"
    fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChallengeInstruction:
    """What the customer must supply to settle an ``otp`` payment.

    Carries no code and no hash. The secret never leaves the provider that minted it,
    and the caller is responsible for storing only its hash.
    """

    kind: str
    sent_to: str
    code_length: int
    expires_in_seconds: int
    max_attempts: int
    resend_cooldown_seconds: int
    secret: str = ""
    delivery_hint: str = ""


@dataclass(frozen=True)
class InitiateResult:
    """The outcome of starting a payment."""

    flow: str
    reference: str
    simulated: bool = False
    redirect: RedirectInstruction | None = None
    challenge: ChallengeInstruction | None = None
    provider_session_id: str = ""
    provider_session_url: str = ""
    notes: str = ""

    def public_dict(self) -> dict[str, Any]:
        """The parts of this result that may cross the API boundary.

        ``challenge.secret`` is deliberately absent: an OTP is never returned to the
        client that asked for it, in any mode, including demo mode.
        """
        data: dict[str, Any] = {
            "flow": self.flow,
            "reference": self.reference,
            "simulated": self.simulated,
        }
        if self.redirect is not None:
            data["redirect"] = {
                "url": self.redirect.url,
                "method": self.redirect.method,
                "fields": dict(self.redirect.fields),
            }
        if self.challenge is not None:
            data["challenge"] = {
                "kind": self.challenge.kind,
                "sentTo": self.challenge.sent_to,
                "codeLength": self.challenge.code_length,
                "expiresInSeconds": self.challenge.expires_in_seconds,
                "maxAttempts": self.challenge.max_attempts,
                "resendCooldownSeconds": self.challenge.resend_cooldown_seconds,
                "deliveryHint": self.challenge.delivery_hint,
            }
        return data


@dataclass(frozen=True)
class ConfirmResult:
    """Whether a proof of payment is genuine, and for how much.

    ``amount`` is what the provider says was actually paid, which is not always what was
    asked for. The caller trusts this over its own expectation so a short payment cannot
    close an order.
    """

    paid: bool
    amount: float = 0.0
    provider_transaction_id: str = ""
    response_code: str = ""
    response_message: str = ""
    signature_valid: bool = True
    already_processed: bool = False


@runtime_checkable
class PaymentProvider(Protocol):
    """The contract. Implementations live beside their integration code."""

    code: str
    label: str
    flow: str

    def is_available(self) -> bool:
        """False when this provider could not take a customer end to end right now."""

    def mode(self) -> str:
        """Which backend is behind it: simulator, mock_otp, sandbox, live, test."""

    def descriptor(self) -> dict[str, Any]:
        """How this provider describes itself to a customer-facing surface."""

    async def initiate(self, context: PaymentContext) -> InitiateResult:
        """Begin a payment. Must not assume it is the first attempt for this order."""

    async def confirm(self, context: PaymentContext, proof: dict[str, Any]) -> ConfirmResult:
        """Decide whether ``proof`` settles the payment described by ``context``."""


class BasePaymentProvider:
    """Shared defaults so each provider only writes what is genuinely its own."""

    code: str = ""
    label: str = ""
    flow: str = FLOW_REDIRECT

    def is_available(self) -> bool:
        return True

    def mode(self) -> str:
        return "live"

    def descriptor(self) -> dict[str, Any]:
        return {
            "provider": self.code,
            "label": self.label,
            "flow": self.flow,
            "mode": self.mode(),
            "available": self.is_available(),
            "simulated": self.mode() in {"simulator", "mock_otp"},
        }

    async def initiate(self, context: PaymentContext) -> InitiateResult:
        raise NotImplementedError(f"{self.code} cannot start a payment.")

    async def confirm(self, context: PaymentContext, proof: dict[str, Any]) -> ConfirmResult:
        raise NotImplementedError(f"{self.code} cannot confirm a payment.")
