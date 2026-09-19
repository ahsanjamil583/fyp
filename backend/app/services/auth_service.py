import secrets
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.password_policy import is_password_acceptable, validate_password_strength
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    ensure_current_session,
    hash_password,
    verify_password,
)
from app.services.otp_service import mark_user_phone_verified, optional_email_to_document, verify_email_otp, verify_phone_otp
from pymongo.errors import DuplicateKeyError

from app.db.mongodb import get_database
from app.services.localization_service import normalize_optional_email, normalize_pk_phone


def user_public(user: dict) -> dict:
    data = {
        "id": str(user["_id"]),
        "fullName": user["fullName"],
        "email": user.get("email") or None,
        "phone": user.get("phone", ""),
        "accountType": user["accountType"],
        "globalRole": user["globalRole"],
        "status": user["status"],
        "isEmailVerified": user.get("isEmailVerified", False),
        "isPhoneVerified": user.get("isPhoneVerified", False),
        "mustResetPassword": bool(user.get("mustResetPassword", False)),
    }
    # A cashier belongs to exactly one business, and the client needs to know which one to
    # send it to its own workspace instead of the owner dashboard.
    if user.get("accountType") == "cashier" and user.get("tenantId"):
        data["tenantId"] = str(user["tenantId"])
    return data


def auth_payload(user: dict) -> dict:
    return {
        "accessToken": create_access_token(user),
        "refreshToken": create_refresh_token(user),
        "tokenType": "bearer",
        "user": user_public(user),
    }


async def find_user_by_email_or_phone(email: str, phone: str) -> dict | None:
    db = get_database()
    normalized_email = normalize_optional_email(email)
    normalized_phone = normalize_pk_phone(phone) if str(phone or "").strip() else ""
    clauses = []
    if normalized_email:
        clauses.append({"email": normalized_email})
    if normalized_phone:
        clauses.append({"phone": normalized_phone})
    return await db.users.find_one({"$or": clauses}) if clauses else None


def duplicate_account_detail(existing: dict, normalized_email: str, normalized_phone: str) -> str:
    email_matches = bool(normalized_email and existing.get("email") == normalized_email)
    phone_matches = bool(normalized_phone and existing.get("phone") == normalized_phone)
    if email_matches and phone_matches:
        return "Email and phone already exist. Sign in instead."
    if phone_matches:
        return "Phone number already exists. Sign in instead."
    if email_matches:
        return "This email is already registered. Please login."
    return "Email or phone already exists. Sign in instead."


async def register_business_owner(payload) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)

    normalized_email = normalize_optional_email(payload.email or "")
    normalized_phone = normalize_pk_phone(payload.phone)
    existing = await find_user_by_email_or_phone(normalized_email, normalized_phone)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=duplicate_account_detail(existing, normalized_email, normalized_phone))

    validate_password_strength(payload.password, normalized_email, normalized_phone, payload.fullName)

    user = {
        "fullName": payload.fullName,
        **optional_email_to_document(normalized_email),
        # users.phone is a unique SPARSE index, which skips a missing field but not an
        # empty string. normalize_pk_phone returns "" for anything it cannot parse, and
        # the schema only checks length, so "abcdefg" arrives here as "". Writing that
        # made the second such registration a duplicate-key 500 - the same defect that
        # was fixed on the cashier path and missed here.
        **({"phone": normalized_phone} if normalized_phone else {}),
        "passwordHash": hash_password(payload.password),
        "accountType": "business_owner",
        "globalRole": "user",
        "status": "active",
        "isEmailVerified": False,
        "isPhoneVerified": False,
        "lastLoginAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        user["_id"] = (await db.users.insert_one(user)).inserted_id
    except DuplicateKeyError as exc:
        # The pre-check cannot see a collision the unique index still rejects, so this
        # answers with a conflict rather than an unhandled 500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with these details already exists. Please login instead.",
        ) from exc
    return auth_payload(user)


async def register_business_owner_with_email_otp(payload) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    normalized_email = normalize_optional_email(payload.email)
    existing = await db.users.find_one({"email": normalized_email})
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already registered. Please login.")

    validate_password_strength(payload.password, normalized_email, payload.fullName)

    verification = await verify_email_otp(
        email=normalized_email,
        code=payload.code,
        account_type="business_owner",
        purpose="register",
        consume=True,
    )
    user = {
        "fullName": payload.fullName,
        "email": normalized_email,
        "passwordHash": hash_password(payload.password),
        "accountType": "business_owner",
        "globalRole": "user",
        "status": "active",
        "isEmailVerified": True,
        "emailVerifiedAt": now,
        "isPhoneVerified": False,
        "lastLoginAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    if payload.businessName:
        user["pendingBusinessName"] = str(payload.businessName).strip()
    try:
        user["_id"] = (await db.users.insert_one(user)).inserted_id
    except DuplicateKeyError as exc:
        # The pre-check cannot see a collision the unique index still rejects, so this
        # answers with a conflict rather than an unhandled 500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with these details already exists. Please login instead.",
        ) from exc
    data = auth_payload(user)
    data["otp"] = verification
    return data


# A real bcrypt hash of a value nobody can log in with, used only to spend the same
# time on an unknown email as on a known one. Computed once at import.
_TIMING_EQUALISER_HASH = hash_password(secrets.token_urlsafe(32))


async def login_user(email: str, password: str, expected_account_type: str | set[str] | None = None) -> dict:
    db = get_database()
    normalized_email = normalize_optional_email(email)
    if not normalized_email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email is required for password login.")
    user = await db.users.find_one({"email": normalized_email})
    # Verify against a dummy hash when the account does not exist. Skipping bcrypt
    # entirely made an unknown email answer in about a millisecond and a known one in
    # about 250, which tells an attacker which addresses are registered.
    if not user:
        verify_password(password, _TIMING_EQUALISER_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    if not verify_password(password, user["passwordHash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active.")

    allowed_account_types = (
        {expected_account_type}
        if isinstance(expected_account_type, str)
        else (set(expected_account_type) if expected_account_type else set())
    )
    if allowed_account_types and user["accountType"] not in allowed_account_types:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account type is not allowed here.")

    # A stored bcrypt hash cannot be tested against the policy, so accounts created before
    # it existed are audited here — the one moment the plaintext is available.
    must_reset = not is_password_acceptable(password, user.get("email"), user.get("phone"), user.get("fullName"))
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"lastLoginAt": now, "updatedAt": now, "mustResetPassword": must_reset}},
    )
    user["mustResetPassword"] = must_reset
    return auth_payload(user)


async def change_password(current_user: dict, current_password: str, new_password: str) -> dict:
    """Change the password of a signed-in account and clear any forced-reset flag."""
    db = get_database()
    if not verify_password(current_password, current_user["passwordHash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")
    if current_password == new_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be different from the current password.",
        )

    validate_password_strength(
        new_password,
        current_user.get("email"),
        current_user.get("phone"),
        current_user.get("fullName"),
    )

    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"passwordHash": hash_password(new_password), "mustResetPassword": False, "updatedAt": now}, "$inc": {"sessionVersion": 1}},
    )
    updated = await db.users.find_one({"_id": current_user["_id"]})
    return auth_payload(updated)


async def revoke_user_sessions(user_id) -> None:
    """End every session for this user by bumping their session version.

    Logout used to return success without doing anything, so a stolen refresh token
    stayed valid for its full seven days after the user had "logged out". Access tokens
    carry the session version and are rejected once it moves.
    """
    db = get_database()
    await db.users.update_one(
        {"_id": user_id},
        {"$inc": {"sessionVersion": 1}, "$set": {"updatedAt": datetime.now(timezone.utc)}},
    )


async def refresh_auth_token(refresh_token: str) -> dict:
    payload = decode_token(refresh_token, expected_type="refresh")
    if not ObjectId.is_valid(payload.get("sub", "")):
        raise HTTPException(status_code=401, detail="Invalid token subject.")
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(payload["sub"]), "status": "active"})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")
    ensure_current_session(payload, user)
    return auth_payload(user)


async def login_user_with_phone_otp(phone: str, code: str, expected_account_type: str) -> dict:
    db = get_database()
    normalized_phone = normalize_pk_phone(phone)
    verification = await verify_phone_otp(
        phone=normalized_phone,
        code=code,
        account_type=expected_account_type,
        purpose="login",
        consume=True,
    )
    user = await db.users.find_one({"phone": normalized_phone, "accountType": expected_account_type, "status": "active"})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found or inactive.")
    await mark_user_phone_verified(user["_id"], normalized_phone)
    user["isPhoneVerified"] = True
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"lastLoginAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc)}},
    )
    data = auth_payload(user)
    data["otp"] = verification
    return data


async def reset_password_with_phone_otp(phone: str, code: str, new_password: str, expected_account_type: str) -> dict:
    db = get_database()
    normalized_phone = normalize_pk_phone(phone)
    user = await db.users.find_one({"phone": normalized_phone, "accountType": expected_account_type, "status": "active"})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found for this phone number.")

    validate_password_strength(new_password, user.get("email"), user.get("phone"), user.get("fullName"))
    verification = await verify_phone_otp(
        phone=normalized_phone,
        code=code,
        account_type=expected_account_type,
        purpose="password_reset",
        consume=True,
    )
    result = await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "passwordHash": hash_password(new_password),
                "isPhoneVerified": True,
                "mustResetPassword": False,
                "updatedAt": datetime.now(timezone.utc),
            },
            "$inc": {"sessionVersion": 1},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found for this phone number.")
    return {"phone": normalized_phone, "maskedPhone": verification["maskedPhone"], "passwordReset": True}


async def reset_password_with_email_otp(email: str, code: str, new_password: str, expected_account_type: str) -> dict:
    db = get_database()
    normalized_email = normalize_optional_email(email)
    user = await db.users.find_one({"email": normalized_email, "accountType": expected_account_type, "status": "active"})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found for this email address.")

    validate_password_strength(new_password, user.get("email"), user.get("phone"), user.get("fullName"))
    verification = await verify_email_otp(
        email=normalized_email,
        code=code,
        account_type=expected_account_type,
        purpose="password_reset",
        consume=True,
    )
    result = await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "passwordHash": hash_password(new_password),
                "isEmailVerified": True,
                "emailVerifiedAt": datetime.now(timezone.utc),
                "mustResetPassword": False,
                "updatedAt": datetime.now(timezone.utc),
            },
            "$inc": {"sessionVersion": 1},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found for this email address.")
    return {"email": normalized_email, "maskedEmail": verification["maskedEmail"], "passwordReset": True}
