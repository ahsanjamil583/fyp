"""Lifecycle of a payment OTP challenge.

The provider mints and checks codes; this module owns everything stateful around them -
storing the hash, expiry, counting attempts, locking, superseding on resend, and sending
the email.

Challenges live in their own ``payment_otp_challenges`` collection rather than in
``otp_challenges``. Keeping them apart means a code minted to settle a payment can never
be presented to a sign-in endpoint, and a sign-in code can never settle a payment, no
matter what either endpoint is asked to do.

One rule runs through all of it: the plaintext code exists only inside
``start_payment_challenge``, long enough to be hashed and emailed. It is never stored,
logged, or returned.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from math import ceil

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.mongodb import get_database
from app.integrations.payments import mock_otp
from app.integrations.payments.provider_base import ChallengeInstruction
from app.services.email_service import EmailSendError, send_payment_otp_email

logger = logging.getLogger(__name__)

CHALLENGE_COLLECTION = "payment_otp_challenges"

STATUS_PENDING = "pending"
STATUS_VERIFIED = "verified"
STATUS_EXPIRED = "expired"
STATUS_LOCKED = "locked"
STATUS_SUPERSEDED = "superseded"


def as_aware_utc(value: datetime | None) -> datetime | None:
    if not value:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _challenge_public(challenge: dict, *, now: datetime | None = None) -> dict:
    """What the client is allowed to know about a live challenge.

    No code, no hash. Only what a countdown and an attempts counter need.
    """
    now = now or datetime.now(timezone.utc)
    expires_at = as_aware_utc(challenge.get("expiresAt"))
    max_attempts = int(challenge.get("maxAttempts", settings.payment_otp_max_attempts))
    attempts = int(challenge.get("attempts", 0))
    resend_count = int(challenge.get("resendCount", 0))
    return {
        "challengeId": str(challenge["_id"]),
        "maskedEmail": challenge.get("maskedEmail", ""),
        "codeLength": mock_otp.PAYMENT_OTP_CODE_LENGTH,
        "expiresAt": expires_at.isoformat() if expires_at else None,
        "expiresInSeconds": max(int((expires_at - now).total_seconds()), 0) if expires_at else 0,
        "attemptsRemaining": max(max_attempts - attempts, 0),
        "maxAttempts": max_attempts,
        "resendCooldownSeconds": max(settings.payment_otp_resend_cooldown_seconds, 0),
        "resendsRemaining": max(int(settings.payment_otp_max_resends) - resend_count, 0),
        "status": challenge.get("status", STATUS_PENDING),
    }


async def _supersede_open_challenges(payment_record_id: ObjectId, now: datetime) -> int:
    """Kill every live code for this payment.

    Called before a new one is issued, so the code in the customer's inbox is always the
    only one that works. Without this, a resend would leave two valid codes alive.
    """
    db = get_database()
    result = await db[CHALLENGE_COLLECTION].update_many(
        {"paymentRecordId": payment_record_id, "status": STATUS_PENDING},
        {"$set": {"status": STATUS_SUPERSEDED, "updatedAt": now}},
    )
    return int(result.modified_count or 0)


async def _enforce_resend_limits(payment_record_id: ObjectId, now: datetime) -> int:
    """Apply the cooldown and the per-payment resend cap.

    Returns how many codes have already been sent for this payment.
    """
    db = get_database()
    latest = await db[CHALLENGE_COLLECTION].find_one(
        {"paymentRecordId": payment_record_id},
        sort=[("createdAt", -1)],
    )
    if not latest:
        return 0

    sent_count = int(latest.get("resendCount", 0)) + 1
    if sent_count > int(settings.payment_otp_max_resends):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many codes were requested for this payment. Start the payment again.",
        )

    cooldown = max(int(settings.payment_otp_resend_cooldown_seconds), 0)
    if cooldown:
        last_sent = as_aware_utc(latest.get("lastSentAt")) or as_aware_utc(latest.get("createdAt")) or now
        elapsed = (now - last_sent).total_seconds()
        if elapsed < cooldown:
            wait_seconds = max(1, int(ceil(cooldown - elapsed)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait_seconds} seconds before requesting another code.",
            )
    return int(latest.get("resendCount", 0))


async def start_payment_challenge(
    *,
    payment_record_id: ObjectId,
    tenant_id: ObjectId,
    transaction_id: ObjectId,
    provider: str,
    challenge: ChallengeInstruction,
    customer_email: str,
    amount: float,
    currency: str,
    business_name: str,
    order_number: str,
    provider_label: str,
    is_resend: bool = False,
) -> dict:
    """Store the hash of a freshly minted code and email the code itself.

    ``challenge.secret`` arrives from the provider, is used twice - once to hash, once to
    send - and is never written anywhere.
    """
    db = get_database()
    now = datetime.now(timezone.utc)

    resend_count = 0
    if is_resend:
        resend_count = await _enforce_resend_limits(payment_record_id, now) + 1
    await _supersede_open_challenges(payment_record_id, now)

    code = challenge.secret
    if not code:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not generate a payment code.")

    document = {
        "paymentRecordId": payment_record_id,
        "tenantId": tenant_id,
        "transactionId": transaction_id,
        "provider": provider,
        # Only the hash is persisted. The code itself is already on its way to the inbox.
        "codeHash": mock_otp.hash_payment_otp_code(str(payment_record_id), code, provider),
        "attempts": 0,
        "maxAttempts": int(settings.payment_otp_max_attempts),
        "status": STATUS_PENDING,
        "expiresAt": now + timedelta(minutes=int(settings.payment_otp_expire_minutes)),
        "resendCount": resend_count,
        "lastSentAt": now,
        "maskedEmail": mock_otp.mask_email(customer_email),
        "deliveryStatus": "queued",
        "createdAt": now,
        "updatedAt": now,
    }
    document["_id"] = (await db[CHALLENGE_COLLECTION].insert_one(document)).inserted_id

    try:
        send_payment_otp_email(
            to_email=customer_email,
            code=code,
            amount=amount,
            currency=currency,
            business_name=business_name,
            order_number=order_number,
            provider_label=provider_label,
        )
    except (EmailSendError, HTTPException) as exc:
        # A challenge nobody can answer is worse than none: mark it dead so the customer
        # is told to retry rather than left staring at a code that never arrives.
        await db[CHALLENGE_COLLECTION].update_one(
            {"_id": document["_id"]},
            {"$set": {"status": STATUS_SUPERSEDED, "deliveryStatus": "failed", "updatedAt": datetime.now(timezone.utc)}},
        )
        logger.error("Payment OTP email failed for record %s: %s", payment_record_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send the payment code by email. Please try again in a moment.",
        ) from exc

    await db[CHALLENGE_COLLECTION].update_one(
        {"_id": document["_id"]},
        {"$set": {"deliveryStatus": "sent", "updatedAt": datetime.now(timezone.utc)}},
    )
    document["deliveryStatus"] = "sent"
    return _challenge_public(document, now=now)


async def get_active_challenge(payment_record_id: ObjectId) -> dict | None:
    db = get_database()
    return await db[CHALLENGE_COLLECTION].find_one(
        {"paymentRecordId": payment_record_id, "status": STATUS_PENDING},
        sort=[("createdAt", -1)],
    )


async def consume_challenge(payment_record_id: ObjectId, provider: str, code: str) -> dict:
    """Check a submitted code, applying expiry, attempts and locking in that order.

    Returns the challenge document on success. Every failure path raises with the status
    the client should act on, and none of them says anything about the expected value.
    """
    db = get_database()
    now = datetime.now(timezone.utc)

    submitted = mock_otp.normalize_payment_otp_code(code)
    if len(submitted) != mock_otp.PAYMENT_OTP_CODE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Enter the {mock_otp.PAYMENT_OTP_CODE_LENGTH}-digit code from your email.",
        )

    challenge = await get_active_challenge(payment_record_id)
    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active payment code was found. Start the payment again.",
        )

    expires_at = as_aware_utc(challenge.get("expiresAt"))
    if expires_at and expires_at < now:
        await db[CHALLENGE_COLLECTION].update_one(
            {"_id": challenge["_id"]},
            {"$set": {"status": STATUS_EXPIRED, "updatedAt": now}},
        )
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This code expired. Request a new one.")

    max_attempts = int(challenge.get("maxAttempts", settings.payment_otp_max_attempts))
    if int(challenge.get("attempts", 0)) >= max_attempts:
        await db[CHALLENGE_COLLECTION].update_one(
            {"_id": challenge["_id"]},
            {"$set": {"status": STATUS_LOCKED, "updatedAt": now}},
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Too many wrong attempts. Request a new code.",
        )

    if not mock_otp.verify_payment_otp_code(str(payment_record_id), submitted, provider, challenge.get("codeHash", "")):
        attempts = int(challenge.get("attempts", 0)) + 1
        remaining = max(max_attempts - attempts, 0)
        update = {"attempts": attempts, "updatedAt": now}
        if remaining <= 0:
            update["status"] = STATUS_LOCKED
        await db[CHALLENGE_COLLECTION].update_one({"_id": challenge["_id"]}, {"$set": update})
        if remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Too many wrong attempts. Request a new code.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
        )

    await db[CHALLENGE_COLLECTION].update_one(
        {"_id": challenge["_id"]},
        {"$set": {"status": STATUS_VERIFIED, "verifiedAt": now, "updatedAt": now}},
    )
    return challenge


async def describe_active_challenge(payment_record_id: ObjectId) -> dict | None:
    challenge = await get_active_challenge(payment_record_id)
    return _challenge_public(challenge) if challenge else None
