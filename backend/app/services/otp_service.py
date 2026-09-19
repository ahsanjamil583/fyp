from __future__ import annotations

import asyncio

import hmac
import secrets
from math import ceil
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.mongodb import get_database
from app.integrations.sms.provider import SmsSendError, send_sms_text
from app.integrations.whatsapp.provider import WhatsAppSendError, send_whatsapp_text
from app.services.email_service import send_otp_email, should_use_email_demo_delivery
from app.services.localization_service import normalize_optional_email, normalize_pk_phone

VALID_ACCOUNT_TYPES = {"business_owner", "customer"}
VALID_PURPOSES = {"login", "register", "verify_phone", "password_reset"}
VALID_CHANNELS = {"sms", "whatsapp", "mock"}


def normalize_account_type(value: str | None) -> str:
    account_type = str(value or "").strip().lower()
    if account_type not in VALID_ACCOUNT_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid account type for OTP.")
    return account_type


def normalize_otp_purpose(value: str | None) -> str:
    purpose = str(value or "login").strip().lower()
    if purpose not in VALID_PURPOSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid OTP purpose.")
    return purpose


def normalize_otp_channel(value: str | None) -> str:
    channel = str(value or "sms").strip().lower()
    if channel not in VALID_CHANNELS:
        return "sms"
    if channel == "mock":
        return "sms"
    return channel


def normalize_otp_code(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def mask_phone(phone: str) -> str:
    normalized = str(phone or "")
    if len(normalized) <= 4:
        return "****"
    return f"{normalized[:4]}****{normalized[-3:]}"


def mask_email(email: str) -> str:
    normalized = normalize_optional_email(email)
    if "@" not in normalized:
        return "****"
    local, domain = normalized.split("@", 1)
    if len(local) <= 2:
        masked_local = f"{local[:1]}***"
    else:
        masked_local = f"{local[:2]}***{local[-1:]}"
    return f"{masked_local}@{domain}"


def hash_otp_code(phone: str, code: str, purpose: str, account_type: str) -> str:
    message = f"{normalize_pk_phone(phone)}:{normalize_otp_code(code)}:{purpose}:{account_type}".encode("utf-8")
    return hmac.new(settings.signing_key.encode("utf-8"), message, sha256).hexdigest()


def verify_otp_hash(phone: str, code: str, purpose: str, account_type: str, expected_hash: str) -> bool:
    candidate = hash_otp_code(phone, code, purpose, account_type)
    return hmac.compare_digest(candidate, str(expected_hash or ""))


def hash_email_otp_code(email: str, code: str, purpose: str, account_type: str) -> str:
    message = f"{normalize_optional_email(email)}:{normalize_otp_code(code)}:{purpose}:{account_type}:email".encode("utf-8")
    return hmac.new(settings.signing_key.encode("utf-8"), message, sha256).hexdigest()


def verify_email_otp_hash(email: str, code: str, purpose: str, account_type: str, expected_hash: str) -> bool:
    candidate = hash_email_otp_code(email, code, purpose, account_type)
    return hmac.compare_digest(candidate, str(expected_hash or ""))


def generate_otp_code() -> str:
    demo_code = str(settings.otp_demo_code or "").strip()
    if settings.otp_demo_mode and demo_code:
        return normalize_otp_code(demo_code).zfill(settings.otp_code_length)[-settings.otp_code_length :]
    max_value = (10**settings.otp_code_length) - 1
    return str(secrets.randbelow(max_value + 1)).zfill(settings.otp_code_length)


def generate_demo_otp_code() -> str:
    demo_code = str(settings.otp_demo_code or "123456").strip()
    return normalize_otp_code(demo_code).zfill(settings.otp_code_length)[-settings.otp_code_length :]


def as_aware_utc(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _otp_message(code: str, purpose: str) -> str:
    reason = {
        "login": "sign in",
        "register": "create your account",
        "verify_phone": "verify your phone number",
        "password_reset": "reset your password",
    }.get(purpose, "continue")
    return f"Your BizXusAI OTP is {code}. Use it to {reason}. It expires in {settings.otp_expire_minutes} minutes."


def build_failed_attempt_update(challenge: dict, now: datetime) -> tuple[dict, int, bool]:
    attempts = int(challenge.get("attempts", 0)) + 1
    max_attempts = int(challenge.get("maxAttempts", settings.otp_max_attempts))
    remaining = max(max_attempts - attempts, 0)
    locked = remaining <= 0
    update = {"attempts": attempts, "updatedAt": now}
    if locked:
        update["status"] = "locked"
    return update, remaining, locked


async def _find_user_by_phone(phone: str, account_type: str) -> dict | None:
    db = get_database()
    return await db.users.find_one({"phone": normalize_pk_phone(phone), "accountType": account_type})


async def _validate_purpose_against_user(phone: str, account_type: str, purpose: str, for_user_id=None) -> None:
    user = await _find_user_by_phone(phone, account_type)

    # Adding a phone number to an account that does not have one yet is the whole point
    # of verify_phone, so requiring the number to already be on a user made it
    # impossible to ever reach: customers never get users.phone set until this succeeds.
    # The caller is authenticated, so what matters is only that the number does not
    # already belong to somebody else.
    if purpose == "verify_phone" and for_user_id is not None:
        if user and user["_id"] != for_user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That phone number is already registered to another account.",
            )
        return

    if purpose in {"login", "password_reset", "verify_phone"} and not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active account found for this phone number.")
    if purpose == "register" and user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account already exists with this phone number. Use phone login instead.")
    if purpose in {"login", "password_reset", "verify_phone"} and user and user.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active.")


async def _find_user_by_email(email: str, account_type: str) -> dict | None:
    db = get_database()
    return await db.users.find_one({"email": normalize_optional_email(email), "accountType": account_type})


async def _validate_email_purpose_against_user(email: str, account_type: str, purpose: str) -> None:
    user = await _find_user_by_email(email, account_type)
    if purpose == "password_reset" and not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active account found for this email address.")
    if purpose == "register" and user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already registered. Please login.")
    if purpose == "password_reset" and user and user.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active.")


async def request_phone_otp(*, phone: str, account_type: str, purpose: str, channel: str = "sms", for_user_id=None) -> dict:
    """Send a phone OTP.

    `for_user_id` is the authenticated user this code is for. It is what lets an account
    verify a number it does not yet have on file.
    """
    db = get_database()
    normalized_phone = normalize_pk_phone(phone)
    account_type = normalize_account_type(account_type)
    purpose = normalize_otp_purpose(purpose)
    channel = normalize_otp_channel(channel)
    await _validate_purpose_against_user(normalized_phone, account_type, purpose, for_user_id)

    now = datetime.now(timezone.utc)
    latest = await db.otp_challenges.find_one(
        {
            "phone": normalized_phone,
            "accountType": account_type,
            "purpose": purpose,
            "status": "pending",
            "expiresAt": {"$gt": now},
        },
        sort=[("createdAt", -1)],
    )
    cooldown = max(settings.otp_resend_cooldown_seconds, 0)
    if latest and cooldown:
        created_at = as_aware_utc(latest.get("createdAt")) or now
        elapsed = (now - created_at).total_seconds()
        if elapsed < cooldown:
            wait_seconds = max(1, int(ceil(cooldown - elapsed)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait_seconds} seconds before requesting another OTP.",
            )

    email_demo_delivery = should_use_email_demo_delivery()
    code = generate_demo_otp_code() if email_demo_delivery else generate_otp_code()
    message_text = _otp_message(code, purpose)
    challenge = {
        "phone": normalized_phone,
        "accountType": account_type,
        "purpose": purpose,
        "channel": channel,
        "codeHash": hash_otp_code(normalized_phone, code, purpose, account_type),
        "attempts": 0,
        "maxAttempts": settings.otp_max_attempts,
        "status": "pending",
        "expiresAt": now + timedelta(minutes=settings.otp_expire_minutes),
        "verifiedAt": None,
        "usedAt": None,
        "deliveryStatus": "queued",
        "createdAt": now,
        "updatedAt": now,
    }
    if email_demo_delivery and settings.otp_return_code_in_response and settings.app_env != "production":
        challenge["debugCode"] = code

    challenge["_id"] = (await db.otp_challenges.insert_one(challenge)).inserted_id

    delivery_status = "mock_sent"
    try:
        if channel == "whatsapp":
            # Without this an unpaired bridge accepts the row and nothing ever collects
            # it: the customer waits for a code that was never going to arrive, with no
            # error anywhere. Falling back to SMS is not possible here because the
            # channel was explicitly requested, so the failure is surfaced instead.
            from app.services.whatsapp_service import whatsapp_connection_status

            integration = await db.whatsapp_integrations.find_one({"provider": settings.whatsapp_provider})
            if not integration or whatsapp_connection_status(integration) != "connected":
                await db.otp_challenges.update_one(
                    {"_id": challenge["_id"]},
                    {"$set": {"deliveryStatus": "failed", "deliveryError": "WhatsApp is not connected.", "updatedAt": datetime.now(timezone.utc)}},
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="WhatsApp is not connected right now. Please request the code by SMS instead.",
                )
            # The bridge claims queued rows by tenantId, as an ObjectId. Sending this
            # under the literal string "system-otp" meant no bridge poll could ever match
            # the row: the customer waited for a code nothing would collect, and because
            # redaction happens on delivery acknowledgement the plaintext code then sat
            # in the log until its TTL expired. It goes out under the tenant whose bridge
            # is actually connected, which is the one the gate above just checked.
            await send_whatsapp_text(
                tenant_id=integration["tenantId"],
                to_phone=normalized_phone,
                message_text=message_text,
                provider=settings.whatsapp_provider,
                raw_context={"purpose": purpose, "accountType": account_type, "source": "otp"},
            )
        else:
            await send_sms_text(
                tenant_id="system-otp",
                to_phone=normalized_phone,
                message_text=message_text,
                provider=settings.sms_provider,
                raw_context={"purpose": purpose, "accountType": account_type, "source": "otp"},
            )
    except (SmsSendError, WhatsAppSendError) as exc:
        delivery_status = "failed"
        await db.otp_challenges.update_one(
            {"_id": challenge["_id"]},
            {"$set": {"deliveryStatus": "failed", "deliveryError": str(exc), "updatedAt": datetime.now(timezone.utc)}},
        )
        # The provider's error text includes the configured SMS gateway URL. It is
        # already stored on the challenge as deliveryError and logged; the caller gets
        # a generic message.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="We could not send the code just now. Please try again in a moment.",
        ) from exc

    await db.otp_challenges.update_one(
        {"_id": challenge["_id"]},
        {"$set": {"deliveryStatus": delivery_status, "updatedAt": datetime.now(timezone.utc)}},
    )

    data = {
        "challengeId": str(challenge["_id"]),
        "phone": normalized_phone,
        "maskedPhone": mask_phone(normalized_phone),
        "accountType": account_type,
        "purpose": purpose,
        "channel": channel,
        "expiresAt": as_aware_utc(challenge["expiresAt"]).isoformat(),
        "expiresInSeconds": max(int((as_aware_utc(challenge["expiresAt"]) - now).total_seconds()), 0),
        "resendCooldownSeconds": max(settings.otp_resend_cooldown_seconds, 0),
        "codeLength": settings.otp_code_length,
        "deliveryStatus": delivery_status,
        "message": "OTP sent successfully.",
    }
    if settings.otp_demo_mode and settings.otp_return_code_in_response and settings.app_env != "production":
        data["debugCode"] = code
        data["demoNote"] = "Development/demo mode only. Do not return OTP codes in production."
    return data


async def request_email_otp(*, email: str, account_type: str, purpose: str) -> dict:
    db = get_database()
    normalized_email = normalize_optional_email(email)
    if not normalized_email or "@" not in normalized_email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid email address.")
    account_type = normalize_account_type(account_type)
    purpose = normalize_otp_purpose(purpose)
    if purpose not in {"register", "password_reset"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email OTP is only available for registration and password reset.")
    await _validate_email_purpose_against_user(normalized_email, account_type, purpose)

    now = datetime.now(timezone.utc)
    latest = await db.otp_challenges.find_one(
        {
            "email": normalized_email,
            "accountType": account_type,
            "purpose": purpose,
            "status": "pending",
            "deliveryStatus": {"$in": ["sent", "demo_sent"]},
            "expiresAt": {"$gt": now},
        },
        sort=[("createdAt", -1)],
    )
    cooldown = max(settings.otp_resend_cooldown_seconds, 0)
    if latest and cooldown:
        created_at = as_aware_utc(latest.get("createdAt")) or now
        elapsed = (now - created_at).total_seconds()
        if elapsed < cooldown:
            wait_seconds = max(1, int(ceil(cooldown - elapsed)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait before requesting another code. Try again in {wait_seconds} seconds.",
            )

    email_demo_delivery = should_use_email_demo_delivery()
    code = generate_demo_otp_code() if email_demo_delivery else generate_otp_code()
    challenge = {
        "email": normalized_email,
        "accountType": account_type,
        "purpose": purpose,
        "channel": "email",
        "codeHash": hash_email_otp_code(normalized_email, code, purpose, account_type),
        "attempts": 0,
        "maxAttempts": settings.otp_max_attempts,
        "status": "pending",
        "expiresAt": now + timedelta(minutes=settings.otp_expire_minutes),
        "verifiedAt": None,
        "usedAt": None,
        "deliveryStatus": "queued",
        "createdAt": now,
        "updatedAt": now,
    }
    if email_demo_delivery and settings.otp_return_code_in_response and settings.app_env != "production":
        challenge["debugCode"] = code

    challenge["_id"] = (await db.otp_challenges.insert_one(challenge)).inserted_id

    delivery_status = "demo_sent" if email_demo_delivery else "sent"
    try:
        # smtplib blocks for up to 20 seconds. On the event loop that stalls every
        # other request on the server, so it runs on a worker thread.
        await asyncio.to_thread(send_otp_email, to_email=normalized_email, code=code)
    except HTTPException:
        await db.otp_challenges.update_one(
            {"_id": challenge["_id"]},
            {"$set": {"deliveryStatus": "failed", "updatedAt": datetime.now(timezone.utc)}},
        )
        raise

    await db.otp_challenges.update_one(
        {"_id": challenge["_id"]},
        {"$set": {"deliveryStatus": delivery_status, "updatedAt": datetime.now(timezone.utc)}},
    )

    data = {
        "challengeId": str(challenge["_id"]),
        "email": normalized_email,
        "maskedEmail": mask_email(normalized_email),
        "accountType": account_type,
        "purpose": purpose,
        "channel": "email",
        "expiresAt": as_aware_utc(challenge["expiresAt"]).isoformat(),
        "expiresInSeconds": max(int((as_aware_utc(challenge["expiresAt"]) - now).total_seconds()), 0),
        "resendCooldownSeconds": max(settings.otp_resend_cooldown_seconds, 0),
        "codeLength": settings.otp_code_length,
        "deliveryStatus": delivery_status,
        "message": "Verification code sent successfully.",
    }
    if email_demo_delivery and settings.otp_return_code_in_response and settings.app_env != "production":
        data["debugCode"] = code
        data["demoNote"] = "Development/demo mode only. Do not return OTP codes in production."
    if email_demo_delivery:
        data["demoNote"] = "Demo OTP mode is active. No real email was sent."
    return data


async def verify_phone_otp(*, phone: str, code: str, account_type: str, purpose: str, consume: bool = False) -> dict:
    db = get_database()
    normalized_phone = normalize_pk_phone(phone)
    account_type = normalize_account_type(account_type)
    purpose = normalize_otp_purpose(purpose)
    normalized_code = normalize_otp_code(code)
    if not normalized_code:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid OTP code.")

    now = datetime.now(timezone.utc)
    challenge = await db.otp_challenges.find_one(
        {
            "phone": normalized_phone,
            "accountType": account_type,
            "purpose": purpose,
            "status": {"$in": ["pending", "verified"]},
        },
        sort=[("createdAt", -1)],
    )
    if not challenge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OTP request not found. Please request a new code.")
    expires_at = as_aware_utc(challenge.get("expiresAt"))
    if expires_at and expires_at < now:
        await db.otp_challenges.update_one({"_id": challenge["_id"]}, {"$set": {"status": "expired", "updatedAt": now}})
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="OTP expired. Please request a new code.")
    already_verified = challenge.get("status") == "verified" and consume is False
    if already_verified and verify_otp_hash(normalized_phone, normalized_code, purpose, account_type, challenge.get("codeHash", "")):
        # Re-checking the hash matters: returning success for ANY code here meant a
        # caller who knew only the phone number could pass a non-consuming verify once
        # the real owner had verified, which is what registration checks against.
        return {
            "challengeId": str(challenge["_id"]),
            "phone": normalized_phone,
            "maskedPhone": mask_phone(normalized_phone),
            "accountType": account_type,
            "purpose": purpose,
            "verified": True,
            "expiresAt": expires_at.isoformat() if expires_at else None,
        }
    if challenge.get("attempts", 0) >= challenge.get("maxAttempts", settings.otp_max_attempts):
        await db.otp_challenges.update_one({"_id": challenge["_id"]}, {"$set": {"status": "locked", "updatedAt": now}})
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Too many wrong OTP attempts. Request a new code.")
    if not verify_otp_hash(normalized_phone, normalized_code, purpose, account_type, challenge.get("codeHash", "")):
        update, remaining, locked = build_failed_attempt_update(challenge, now)
        await db.otp_challenges.update_one({"_id": challenge["_id"]}, {"$set": update})
        if locked:
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Too many wrong OTP attempts. Request a new code.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid OTP code. {remaining} attempts remaining.")

    new_status = "used" if consume else "verified"
    update = {
        "status": new_status,
        "verifiedAt": challenge.get("verifiedAt") or now,
        "updatedAt": now,
    }
    if consume:
        update["usedAt"] = now
    await db.otp_challenges.update_one({"_id": challenge["_id"]}, {"$set": update})
    return {
        "challengeId": str(challenge["_id"]),
        "phone": normalized_phone,
        "maskedPhone": mask_phone(normalized_phone),
        "accountType": account_type,
        "purpose": purpose,
        "verified": True,
        "consumed": consume,
        "expiresAt": expires_at.isoformat() if expires_at else None,
    }


async def verify_email_otp(*, email: str, code: str, account_type: str, purpose: str, consume: bool = False) -> dict:
    db = get_database()
    normalized_email = normalize_optional_email(email)
    if not normalized_email or "@" not in normalized_email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid email address.")
    account_type = normalize_account_type(account_type)
    purpose = normalize_otp_purpose(purpose)
    normalized_code = normalize_otp_code(code)
    if len(normalized_code) != settings.otp_code_length:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Enter a {settings.otp_code_length}-digit verification code.")

    now = datetime.now(timezone.utc)
    challenge = await db.otp_challenges.find_one(
        {
            "email": normalized_email,
            "accountType": account_type,
            "purpose": purpose,
            "status": {"$in": ["pending", "verified"]},
        },
        sort=[("createdAt", -1)],
    )
    if not challenge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification request not found. Please request a new code.")
    expires_at = as_aware_utc(challenge.get("expiresAt"))
    if expires_at and expires_at < now:
        await db.otp_challenges.update_one({"_id": challenge["_id"]}, {"$set": {"status": "expired", "updatedAt": now}})
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Verification code expired. Please request a new one.")
    already_verified = challenge.get("status") == "verified" and consume is False
    if already_verified and verify_email_otp_hash(normalized_email, normalized_code, purpose, account_type, challenge.get("codeHash", "")):
        # See the phone path above: the hash check is what makes "already verified"
        # mean "this caller verified it", not "somebody did".
        return {
            "challengeId": str(challenge["_id"]),
            "email": normalized_email,
            "maskedEmail": mask_email(normalized_email),
            "accountType": account_type,
            "purpose": purpose,
            "verified": True,
            "expiresAt": expires_at.isoformat() if expires_at else None,
        }
    if challenge.get("attempts", 0) >= challenge.get("maxAttempts", settings.otp_max_attempts):
        await db.otp_challenges.update_one({"_id": challenge["_id"]}, {"$set": {"status": "locked", "updatedAt": now}})
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Too many wrong OTP attempts. Request a new code.")
    if not verify_email_otp_hash(normalized_email, normalized_code, purpose, account_type, challenge.get("codeHash", "")):
        update, remaining, locked = build_failed_attempt_update(challenge, now)
        await db.otp_challenges.update_one({"_id": challenge["_id"]}, {"$set": update})
        if locked:
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Too many wrong OTP attempts. Request a new code.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code.")

    new_status = "used" if consume else "verified"
    update = {
        "status": new_status,
        "verifiedAt": challenge.get("verifiedAt") or now,
        "updatedAt": now,
    }
    if consume:
        update["usedAt"] = now
    await db.otp_challenges.update_one({"_id": challenge["_id"]}, {"$set": update})
    return {
        "challengeId": str(challenge["_id"]),
        "email": normalized_email,
        "maskedEmail": mask_email(normalized_email),
        "accountType": account_type,
        "purpose": purpose,
        "verified": True,
        "consumed": consume,
        "expiresAt": expires_at.isoformat() if expires_at else None,
    }


async def mark_user_email_verified(user_id, email: str) -> None:
    db = get_database()
    normalized_user_id = ObjectId(user_id) if isinstance(user_id, str) and ObjectId.is_valid(user_id) else user_id
    await db.users.update_one(
        {"_id": normalized_user_id},
        {"$set": {"email": normalize_optional_email(email), "isEmailVerified": True, "emailVerifiedAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc)}},
    )


async def mark_user_phone_verified(user_id, phone: str) -> None:
    db = get_database()
    normalized_user_id = ObjectId(user_id) if isinstance(user_id, str) and ObjectId.is_valid(user_id) else user_id
    await db.users.update_one(
        {"_id": normalized_user_id},
        {"$set": {"phone": normalize_pk_phone(phone), "isPhoneVerified": True, "phoneVerifiedAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc)}},
    )


def optional_email_to_document(email: str | None) -> dict:
    normalized = normalize_optional_email(email or "")
    return {"email": normalized} if normalized else {}
