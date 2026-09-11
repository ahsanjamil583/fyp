"""Easypaisa hosted checkout (Easypay redirect).

The customer's browser is sent to Easypay with the order parameters and an encrypted
request hash. After paying, Easypay POSTs the result to ``postBackURL``.

Unlike JazzCash's HMAC, Easypay's ``merchantHashedRequest`` is the parameter string
encrypted with AES-128-ECB under the store's 16-character hash key, base64 encoded.

Reference: Easypaisa Easypay Merchant Integration Guide.
"""

from __future__ import annotations

import base64
import hmac

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.core.config import settings

SANDBOX_CHECKOUT_URL = "https://easypaystg.easypaisa.com.pk/easypay/Index.jsf"
LIVE_CHECKOUT_URL = "https://easypay.easypaisa.com.pk/easypay/Index.jsf"

AES_BLOCK_SIZE = 16
SUCCESS_RESPONSE_CODE = "0000"
# Easypay reports an already-completed order rather than paying it twice.
ALREADY_PAID_RESPONSE_CODE = "0001"

# Easypay signs these fields, in this order. The order is part of the contract: the
# gateway rebuilds the same string on its side and any reordering fails the hash.
HASHED_FIELDS = ("amount", "autoRedirect", "emailAddr", "expiryDate", "mobileNum", "orderRefNum", "paymentMethod", "postBackURL", "storeId")


def checkout_url() -> str:
    return LIVE_CHECKOUT_URL if settings.easypaisa_mode == "live" else SANDBOX_CHECKOUT_URL


def _pkcs5_pad(data: bytes) -> bytes:
    padding = AES_BLOCK_SIZE - (len(data) % AES_BLOCK_SIZE)
    return data + bytes([padding]) * padding


def encrypt_request(parameters: str, hash_key: str = "") -> str:
    """AES-128-ECB encrypt the parameter string, base64 encoded.

    ECB is not a mode anyone would choose today, but it is what the Easypay contract
    specifies, so the request has to match it exactly.
    """
    key = (hash_key or settings.easypaisa_hash_key).encode("utf-8")
    if len(key) != AES_BLOCK_SIZE:
        raise ValueError("Easypaisa hash key must be exactly 16 characters.")
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    encrypted = encryptor.update(_pkcs5_pad(parameters.encode("utf-8"))) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")


def _hashable_string(fields: dict[str, str]) -> str:
    return "&".join(f"{key}={fields.get(key, '')}" for key in HASHED_FIELDS if str(fields.get(key, "")).strip() != "")


def build_checkout_request(
    *,
    order_ref: str,
    amount: float,
    post_back_url: str,
    expiry: str,
    customer_email: str = "",
    customer_mobile: str = "",
) -> dict:
    """Build the redirect Easypay expects."""
    fields = {
        "storeId": settings.easypaisa_store_id,
        # Easypay wants a plain decimal with two places and no thousands separator.
        "amount": f"{float(amount):.2f}",
        "postBackURL": post_back_url,
        "orderRefNum": order_ref,
        "expiryDate": expiry,
        "merchantPaymentMethod": "",
        "emailAddr": customer_email,
        "mobileNum": customer_mobile,
        "paymentMethod": "",
        "autoRedirect": "1",
    }
    hashed = encrypt_request(_hashable_string(fields))
    fields["merchantHashedReq"] = hashed
    return {"url": checkout_url(), "method": "GET", "fields": fields}


def verify_callback(payload: dict[str, str], hash_key: str = "") -> dict:
    """Validate an Easypay result before treating it as a payment.

    Easypay returns the same encrypted hash it was given, so the check is that the hash
    on the response matches one computed from the returned fields. A response with no
    hash is never accepted as paid: this endpoint is public.
    """
    response_code = str(payload.get("status") or payload.get("responseCode") or "").strip()
    received_hash = str(payload.get("merchantHashedReq") or payload.get("hashKey") or "").strip()

    signature_valid = False
    if received_hash:
        try:
            expected = encrypt_request(_hashable_string({key: str(value) for key, value in payload.items()}), hash_key)
            signature_valid = hmac.compare_digest(received_hash, expected)
        except ValueError:
            signature_valid = False

    try:
        amount = float(str(payload.get("amount") or 0) or 0)
    except ValueError:
        amount = 0.0

    return {
        "signatureValid": signature_valid,
        "paid": signature_valid and response_code in {SUCCESS_RESPONSE_CODE, ALREADY_PAID_RESPONSE_CODE},
        "txnRef": str(payload.get("orderRefNum") or ""),
        "amount": amount,
        "providerTransactionId": str(payload.get("transactionId") or payload.get("paymentToken") or ""),
        "responseCode": response_code,
        "responseMessage": str(payload.get("desc") or payload.get("responseDesc") or ""),
    }
