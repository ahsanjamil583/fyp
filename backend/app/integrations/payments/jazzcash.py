"""JazzCash hosted checkout (Page Redirection / "MWALLET" merchant form).

The customer's browser POSTs a signed form to JazzCash, pays there, and JazzCash POSTs
the result back to ``pp_ReturnURL``. Both directions are signed with the same
HMAC-SHA256 scheme, so the same builder verifies the response.

Reference: JazzCash Merchant Integration Guide, "HTTP POST (Page Redirection)".
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from app.core.config import settings

SANDBOX_CHECKOUT_URL = "https://sandbox.jazzcash.com.pk/CustomerPortal/transactionmanagement/merchantform/"
LIVE_CHECKOUT_URL = "https://payments.jazzcash.com.pk/CustomerPortal/transactionmanagement/merchantform/"

# JazzCash timestamps are Pakistan local time in this exact layout, with no separators.
TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"
PAKISTAN_UTC_OFFSET_HOURS = 5

SUCCESS_RESPONSE_CODE = "000"
# JazzCash reports a duplicate of an already-successful transaction with its own code.
ALREADY_PAID_RESPONSE_CODE = "121"


def checkout_url() -> str:
    return LIVE_CHECKOUT_URL if settings.jazzcash_mode == "live" else SANDBOX_CHECKOUT_URL


def _pakistan_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=PAKISTAN_UTC_OFFSET_HOURS)


def secure_hash(fields: dict[str, str], integrity_salt: str = "") -> str:
    """Sign the request or verify a response.

    JazzCash sorts the ``pp_`` fields by key, drops empty values, joins them with "&",
    prefixes the integrity salt, and takes an HMAC-SHA256 keyed by that same salt. Empty
    values must be dropped rather than sent as empty strings, because the gateway
    computes its side the same way and any difference silently fails the whole payment.
    """
    salt = integrity_salt or settings.jazzcash_integrity_salt
    signed_keys = sorted(key for key in fields if key.lower().startswith(("pp_", "ppmpf_")))
    values = [str(fields[key]) for key in signed_keys if str(fields.get(key, "")).strip() != ""]
    message = "&".join([salt, *values])
    return hmac.new(salt.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest().upper()


def build_checkout_request(
    *,
    txn_ref: str,
    amount: float,
    return_url: str,
    bill_reference: str,
    description: str,
    customer_mobile: str = "",
    customer_email: str = "",
    expiry_minutes: int = 60,
) -> dict:
    """Build the form the customer's browser POSTs to JazzCash."""
    now = _pakistan_now()
    fields = {
        "pp_Version": "1.1",
        "pp_TxnType": "MWALLET",
        "pp_Language": "EN",
        "pp_MerchantID": settings.jazzcash_merchant_id,
        "pp_SubMerchantID": "",
        "pp_Password": settings.jazzcash_password,
        "pp_BankID": "",
        "pp_ProductID": "",
        "pp_TxnRefNo": txn_ref,
        # JazzCash amounts are in paisa, as an integer string with no separators.
        "pp_Amount": str(int(round(float(amount) * 100))),
        "pp_TxnCurrency": "PKR",
        "pp_TxnDateTime": now.strftime(TIMESTAMP_FORMAT),
        "pp_BillReference": bill_reference or txn_ref,
        "pp_Description": (description or "BizXusAI order")[:100],
        "pp_TxnExpiryDateTime": (now + timedelta(minutes=expiry_minutes)).strftime(TIMESTAMP_FORMAT),
        "pp_ReturnURL": return_url,
        "ppmpf_1": customer_mobile,
        "ppmpf_2": customer_email,
        "ppmpf_3": "",
        "ppmpf_4": "",
        "ppmpf_5": "",
    }
    fields["pp_SecureHash"] = secure_hash(fields)
    return {"url": checkout_url(), "method": "POST", "fields": fields}


def verify_callback(payload: dict[str, str], integrity_salt: str = "") -> dict:
    """Check the signature JazzCash sent back, then read the outcome.

    An unsigned or wrongly signed callback is treated as a failure and never as a
    payment: this endpoint is publicly reachable, so the signature is the only thing
    separating a real confirmation from anyone posting a success code.
    """
    received_hash = str(payload.get("pp_SecureHash") or "").upper()
    fields = {key: value for key, value in payload.items() if key != "pp_SecureHash"}
    expected_hash = secure_hash(fields, integrity_salt)
    signature_valid = bool(received_hash) and hmac.compare_digest(received_hash, expected_hash)

    response_code = str(payload.get("pp_ResponseCode") or "").strip()
    paid = signature_valid and response_code in {SUCCESS_RESPONSE_CODE, ALREADY_PAID_RESPONSE_CODE}
    amount_raw = str(payload.get("pp_Amount") or "0").strip() or "0"
    try:
        amount = int(amount_raw) / 100
    except ValueError:
        amount = 0.0

    return {
        "signatureValid": signature_valid,
        # The HMAC is computed over every pp_ field including pp_ResponseCode, so a
        # verified signature really does attest to the outcome and not just the request.
        "outcomeSigned": True,
        "paid": paid,
        "txnRef": str(payload.get("pp_TxnRefNo") or ""),
        "amount": amount,
        "providerTransactionId": str(payload.get("pp_RetreivalReferenceNo") or payload.get("pp_AuthCode") or ""),
        "responseCode": response_code,
        "responseMessage": str(payload.get("pp_ResponseMessage") or ""),
    }
