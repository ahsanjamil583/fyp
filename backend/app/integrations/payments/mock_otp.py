"""Code generation and verification for the mock OTP wallet flow.

Deliberately separate from ``app.services.otp_service``, which handles sign-in codes.
Sharing that module looked tempting and would have been wrong three times over:

* ``generate_otp_code`` there returns ``OTP_DEMO_CODE`` (123456) whenever demo mode is
  on, so every payment would have had the same predictable code;
* ``send_otp_email`` there sends nothing at all in demo mode, logging the code instead;
* its challenges are keyed by ``(phone|email, accountType, purpose)`` drawn from a closed
  set that has no payment purpose - widening it would have let anyone mint a
  payment-grade challenge through the public ``/auth/otp/request`` endpoint.

So this module reuses the *technique* - HMAC-SHA256 under the server signing key,
constant-time comparison - and none of the code. A code minted here is bound to one
payment record, so it cannot be replayed against another payment or against a login.

Everything here is pure: no database, no clock beyond what is passed in, no settings
except the code length and the signing key. That keeps it testable without Mongo.
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256

from app.core.config import settings

PAYMENT_OTP_CODE_LENGTH = 6


def generate_payment_otp_code() -> str:
    """A fresh random code, every time, in every mode.

    This never consults ``OTP_DEMO_MODE`` or ``OTP_DEMO_CODE``. A payment that could be
    settled with a code someone already knows is not a demonstration of a payment
    system, and the test suite asserts this directly.
    """
    upper_bound = 10**PAYMENT_OTP_CODE_LENGTH
    return str(secrets.randbelow(upper_bound)).zfill(PAYMENT_OTP_CODE_LENGTH)


def normalize_payment_otp_code(value: str | None) -> str:
    """Keep the digits and drop the rest, so "483 920" and "483-920" both work."""
    return "".join(character for character in str(value or "") if character.isdigit())


def hash_payment_otp_code(payment_record_id: str, code: str, provider: str) -> str:
    """Bind a code to exactly one payment record and provider.

    The record id is part of the signed message, so a code issued for one payment does
    not verify against another even if both were minted in the same second.
    """
    message = f"{payment_record_id}:{normalize_payment_otp_code(code)}:{provider}:payment_otp".encode("utf-8")
    return hmac.new(settings.signing_key.encode("utf-8"), message, sha256).hexdigest()


def verify_payment_otp_code(payment_record_id: str, code: str, provider: str, expected_hash: str) -> bool:
    """Constant-time check, so a wrong code leaks nothing through timing."""
    candidate = hash_payment_otp_code(payment_record_id, code, provider)
    return hmac.compare_digest(candidate, str(expected_hash or ""))


def mask_email(email: str) -> str:
    """Enough of an address to recognise, not enough to learn it."""
    normalized = str(email or "").strip().lower()
    if "@" not in normalized:
        return "****"
    local, domain = normalized.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[:1]}***"
    else:
        masked_local = f"{local[:2]}***{local[-1:]}"
    return f"{masked_local}@{domain}"


def mask_mobile(mobile: str) -> str:
    normalized = str(mobile or "").strip()
    if len(normalized) <= 4:
        return "****"
    return f"{normalized[:4]}****{normalized[-3:]}"


def build_mock_transaction_id(reference: str) -> str:
    """A provider-style reference for the settled payment.

    Prefixed so nobody mistakes a demo settlement for a real wallet transaction, either
    in the database or on a printed receipt.
    """
    tail = str(reference or "").strip()[-10:].upper() or secrets.token_hex(5).upper()
    return f"MOCKOTP{tail}"
