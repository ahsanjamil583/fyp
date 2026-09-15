"""One interface over the redirect payment gateways.

``payment_service`` asks this module for "where do I send the customer" and "is this
callback a real payment", and does not care which gateway or which mode is behind it.

The simulator is deliberately not a separate code path at the verification end: it
builds its callback with the same signing functions the real gateways use, so the
signature check that protects production is the one exercised during local testing. Only
the destination of the redirect changes between simulator, sandbox, and live.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import MOCK_GATEWAY_MODES, settings
from app.integrations.payments import easypaisa, jazzcash

# Used only when a gateway runs in simulator mode, where no merchant credentials exist.
# They are not secrets: the simulator is unreachable in production, which the settings
# validator enforces.
SIMULATOR_JAZZCASH_SALT = "bizxus_simulator_jazzcash_salt"
SIMULATOR_EASYPAISA_KEY = "BizXusSimKey1234"  # Easypay keys are exactly 16 characters.

GATEWAY_PROVIDERS = ("jazzcash", "easypaisa")


class PaymentGatewayError(Exception):
    """A gateway could not be prepared, with a message safe to show a customer."""


def gateway_mode(provider: str) -> str:
    if provider == "jazzcash":
        return settings.effective_jazzcash_mode
    if provider == "easypaisa":
        return settings.effective_easypaisa_mode
    raise PaymentGatewayError(f"Unknown payment gateway '{provider}'.")


def is_simulated(provider: str) -> bool:
    """True when this gateway is the hosted simulator page."""
    return gateway_mode(provider) == "simulator"


def uses_mock_credentials(provider: str) -> bool:
    """True for any local stand-in mode, which has no merchant credentials.

    Both `simulator` and `mock_otp` are local: neither has been issued a salt or a hash
    key, so both must fall back to the placeholder ones. Keying this off `is_simulated`
    alone meant a server in `mock_otp` mode reached for an empty real key and failed to
    sign at all.
    """
    return gateway_mode(provider) in MOCK_GATEWAY_MODES


def jazzcash_salt() -> str:
    return SIMULATOR_JAZZCASH_SALT if uses_mock_credentials("jazzcash") else settings.jazzcash_integrity_salt


def easypaisa_key() -> str:
    return SIMULATOR_EASYPAISA_KEY if uses_mock_credentials("easypaisa") else settings.easypaisa_hash_key


def gateway_label(provider: str) -> str:
    return {"jazzcash": "JazzCash", "easypaisa": "Easypaisa"}.get(provider, provider.title())


def build_checkout(
    provider: str,
    *,
    txn_ref: str,
    amount: float,
    return_url: str,
    bill_reference: str,
    description: str,
    customer_mobile: str = "",
    customer_email: str = "",
) -> dict[str, Any]:
    """Describe the redirect that takes the customer to the gateway.

    Returns ``{"url", "method", "fields"}``. A POST gateway needs an auto-submitting
    form, which is why the method travels with the request rather than being assumed.
    """
    if provider not in GATEWAY_PROVIDERS:
        raise PaymentGatewayError(f"Unknown payment gateway '{provider}'.")

    if is_simulated(provider):
        # The simulator is served by this API, so the redirect is a plain GET.
        return {
            "url": f"{_api_base_url()}/payments/{provider}/simulator/{txn_ref}",
            "method": "GET",
            "fields": {},
            "simulated": True,
        }

    if provider == "jazzcash":
        request = jazzcash.build_checkout_request(
            txn_ref=txn_ref,
            amount=amount,
            return_url=return_url,
            bill_reference=bill_reference,
            description=description,
            customer_mobile=customer_mobile,
            customer_email=customer_email,
        )
    else:
        request = easypaisa.build_checkout_request(
            order_ref=txn_ref,
            amount=amount,
            post_back_url=return_url,
            expiry=(datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y%m%d %H%M%S"),
            customer_email=customer_email,
            customer_mobile=customer_mobile,
        )
    return {**request, "simulated": False}


def verify_callback(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Decide whether a callback really represents a completed payment."""
    if provider == "jazzcash":
        return jazzcash.verify_callback(payload, integrity_salt=jazzcash_salt())
    if provider == "easypaisa":
        return easypaisa.verify_callback(payload, hash_key=easypaisa_key())
    raise PaymentGatewayError(f"Unknown payment gateway '{provider}'.")


def build_simulated_callback(provider: str, *, txn_ref: str, amount: float, approve: bool) -> dict[str, str]:
    """Produce a signed callback exactly as the gateway would.

    Signing here rather than short-circuiting the check is the point of the simulator:
    a bug in the signature code fails locally instead of in production.
    """
    if provider == "jazzcash":
        payload = {
            "pp_TxnRefNo": txn_ref,
            "pp_Amount": str(int(round(float(amount) * 100))),
            "pp_TxnCurrency": "PKR",
            "pp_ResponseCode": jazzcash.SUCCESS_RESPONSE_CODE if approve else "124",
            "pp_ResponseMessage": "Thank you for using JazzCash." if approve else "Transaction cancelled by user.",
            "pp_RetreivalReferenceNo": f"SIM{txn_ref[-10:]}",
            "pp_MerchantID": settings.jazzcash_merchant_id or "SIMULATOR",
        }
        payload["pp_SecureHash"] = jazzcash.secure_hash(payload, jazzcash_salt())
        return payload

    if provider == "easypaisa":
        payload = {
            "orderRefNum": txn_ref,
            "amount": f"{float(amount):.2f}",
            "status": easypaisa.SUCCESS_RESPONSE_CODE if approve else "0002",
            "desc": "Payment completed." if approve else "Payment cancelled by user.",
            "transactionId": f"SIM{txn_ref[-10:]}",
            "storeId": settings.easypaisa_store_id or "SIMULATOR",
        }
        payload["merchantHashedReq"] = easypaisa.encrypt_request(
            easypaisa._hashable_string(payload), easypaisa_key()
        )
        return payload

    raise PaymentGatewayError(f"Unknown payment gateway '{provider}'.")


def _api_base_url() -> str:
    """Base URL a browser (and a gateway's servers) can use to reach this API.

    BACKEND_PUBLIC_URL ships as a placeholder in .env.example, and a placeholder here
    would send customers to a domain that does not exist. Anything that still looks like
    the sample value is ignored in favour of the local address.
    """
    base = (settings.backend_public_url or "").rstrip("/")
    if not base or "example.com" in base or "your-" in base:
        base = f"http://localhost:{settings.port}"
    return f"{base}{settings.api_v1_prefix}"


def gateway_status(provider: str) -> dict[str, Any]:
    """Readiness of one gateway, for the dashboard and readiness report."""
    mode = gateway_mode(provider)
    configured = settings.jazzcash_configured if provider == "jazzcash" else settings.easypaisa_configured
    requested = settings.jazzcash_mode if provider == "jazzcash" else settings.easypaisa_mode
    return {
        "provider": provider,
        "label": gateway_label(provider),
        "mode": mode,
        "requestedMode": requested,
        "credentialsConfigured": configured,
        "usingSimulator": mode == "simulator",
        "fellBackToSimulator": requested != mode,
    }
