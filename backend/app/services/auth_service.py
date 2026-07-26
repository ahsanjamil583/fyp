from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.services.otp_service import mark_user_phone_verified, optional_email_to_document, verify_email_otp, verify_phone_otp
from app.db.mongodb import get_database
from app.services.localization_service import normalize_optional_email, normalize_pk_phone


def user_public(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "fullName": user["fullName"],
        "email": user.get("email") or None,
        "phone": user.get("phone", ""),
        "accountType": user["accountType"],
        "globalRole": user["globalRole"],
        "status": user["status"],
        "isEmailVerified": user.get("isEmailVerified", False),
        "isPhoneVerified": user.get("isPhoneVerified", False),
    }


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
        return "Phone number already exists. Use phone OTP login instead."
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

    user = {
        "fullName": payload.fullName,
        **optional_email_to_document(normalized_email),
        "phone": normalized_phone,
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
    user["_id"] = (await db.users.insert_one(user)).inserted_id
    return auth_payload(user)


async def register_business_owner_with_email_otp(payload) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    normalized_email = normalize_optional_email(payload.email)
    existing = await db.users.find_one({"email": normalized_email})
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already registered. Please login.")

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
    user["_id"] = (await db.users.insert_one(user)).inserted_id
    data = auth_payload(user)
    data["otp"] = verification
    return data


async def login_user(email: str, password: str, expected_account_type: str | None = None) -> dict:
    db = get_database()
    normalized_email = normalize_optional_email(email)
    if not normalized_email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email is required for password login.")
    user = await db.users.find_one({"email": normalized_email})
    if not user or not verify_password(password, user["passwordHash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active.")

    if expected_account_type and user["accountType"] != expected_account_type:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account type is not allowed here.")

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"lastLoginAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc)}},
    )
    return auth_payload(user)


async def refresh_auth_token(refresh_token: str) -> dict:
    payload = decode_token(refresh_token, expected_type="refresh")
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(payload["sub"]), "status": "active"})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")
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
    verification = await verify_phone_otp(
        phone=normalized_phone,
        code=code,
        account_type=expected_account_type,
        purpose="password_reset",
        consume=True,
    )
    result = await db.users.update_one(
        {"phone": normalized_phone, "accountType": expected_account_type, "status": "active"},
        {"$set": {"passwordHash": hash_password(new_password), "isPhoneVerified": True, "updatedAt": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found for this phone number.")
    return {"phone": normalized_phone, "maskedPhone": verification["maskedPhone"], "passwordReset": True}


async def reset_password_with_email_otp(email: str, code: str, new_password: str, expected_account_type: str) -> dict:
    db = get_database()
    normalized_email = normalize_optional_email(email)
    verification = await verify_email_otp(
        email=normalized_email,
        code=code,
        account_type=expected_account_type,
        purpose="password_reset",
        consume=True,
    )
    result = await db.users.update_one(
        {"email": normalized_email, "accountType": expected_account_type, "status": "active"},
        {
            "$set": {
                "passwordHash": hash_password(new_password),
                "isEmailVerified": True,
                "emailVerifiedAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found for this email address.")
    return {"email": normalized_email, "maskedEmail": verification["maskedEmail"], "passwordReset": True}
