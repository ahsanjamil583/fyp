from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.password_policy import validate_password_strength
from app.core.security import hash_password
from app.db.mongodb import get_database
from app.services.auth_service import auth_payload, duplicate_account_detail, find_user_by_email_or_phone
from app.services.customer_service import sync_registered_customer_records
from app.services.localization_service import normalize_optional_email, normalize_optional_pk_phone
from app.services.otp_service import verify_email_otp


def profile_public(profile: dict) -> dict:
    return {
        "id": str(profile["_id"]),
        "userId": profile["userId"],
        "phone": profile["phone"],
        "defaultAddress": profile.get("defaultAddress", {}),
        "savedAddresses": profile.get("savedAddresses", []),
        "preferences": profile.get("preferences", {}),
        "createdAt": profile["createdAt"].isoformat(),
        "updatedAt": profile["updatedAt"].isoformat(),
    }


async def register_customer(payload) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)

    normalized_email = normalize_optional_email(payload.email)
    normalized_phone = ""
    existing = await find_user_by_email_or_phone(normalized_email, normalized_phone)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=duplicate_account_detail(existing, normalized_email, normalized_phone))

    validate_password_strength(payload.password, normalized_email, normalized_phone, payload.fullName)
    # Consume the code BEFORE creating anything. Verifying without consuming, inserting,
    # then consuming left the account behind whenever the consuming check failed, so a
    # wrong code still created a row that blocked the real owner with a 409.
    verification = await verify_email_otp(
        email=normalized_email,
        code=payload.code,
        account_type="customer",
        purpose="register",
        consume=True,
    )

    user = {
        "fullName": payload.fullName,
        "email": normalized_email,
        "passwordHash": hash_password(payload.password),
        "accountType": "customer",
        "globalRole": "user",
        "status": "active",
        "isEmailVerified": True,
        "emailVerifiedAt": now,
        "isPhoneVerified": False,
        "lastLoginAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    if normalized_phone:
        user["phone"] = normalized_phone
    try:
        user["_id"] = (await db.users.insert_one(user)).inserted_id
        await db.customer_profiles.insert_one(
            {
                "userId": str(user["_id"]),
                "phone": normalized_phone,
                "defaultAddress": {},
                "savedAddresses": [],
                "preferences": {},
                "createdAt": now,
                "updatedAt": now,
            }
        )
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email is already registered. Please login.") from exc
    await sync_registered_customer_records(
        customer_user_id=user["_id"],
        name=user["fullName"],
        phone=user.get("phone", ""),
        email=user.get("email", ""),
        source_tag="customer_portal",
        # The email was just proved by the registration OTP. The phone was only typed
        # in, so it must not be used to claim anyone else's guest records.
        email_verified=True,
        phone_verified=bool(user.get("isPhoneVerified")),
    )
    data = auth_payload(user)
    data["otp"] = verification
    return data


async def get_customer_profile(user_id: str) -> dict:
    db = get_database()
    profile = await db.customer_profiles.find_one({"userId": user_id})
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer profile not found.")
    return profile_public(profile)


async def update_customer_profile(user_id: str, payload) -> dict:
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer user not found.")
    update = {
        "defaultAddress": payload.defaultAddress,
        "savedAddresses": payload.savedAddresses,
        "preferences": payload.preferences,
        "updatedAt": datetime.now(timezone.utc),
    }
    if payload.phone:
        update["phone"] = normalize_optional_pk_phone(payload.phone)

    await db.customer_profiles.update_one({"userId": user_id}, {"$set": update})
    profile_phone = update.get("phone") or user.get("phone", "")
    # isPhoneVerified refers to the number on the USER record, not to whatever was just
    # typed into the profile. Passing the new number alongside the old number's flag let
    # someone verify their own phone once and then claim a stranger's guest records by
    # typing that stranger's number in. The flag only counts when the two agree.
    phone_is_verified = bool(user.get("isPhoneVerified")) and profile_phone == user.get("phone", "")
    await sync_registered_customer_records(
        customer_user_id=user["_id"],
        name=user.get("fullName", ""),
        phone=profile_phone,
        email=user.get("email", ""),
        address=payload.defaultAddress or {},
        source_tag="customer_portal",
        # A profile save proves nothing about the details typed into it. Only details
        # this account has actually verified may claim guest records.
        email_verified=bool(user.get("isEmailVerified")),
        phone_verified=phone_is_verified,
    )
    return await get_customer_profile(user_id)
