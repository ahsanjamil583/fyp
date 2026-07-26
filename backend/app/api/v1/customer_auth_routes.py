from fastapi import APIRouter, Depends

from app.core.responses import success_response
from app.core.security import get_current_customer_user
from app.schemas.auth_schema import LoginRequest, RefreshTokenRequest
from app.schemas.customer_auth_schema import CustomerProfileUpdateRequest, CustomerRegisterRequest
from app.schemas.otp_schema import (
    PhoneCustomerRegisterRequest,
    PhoneOtpLoginRequest,
    PhoneOtpRequest,
    PhoneOtpVerifyRequest,
    PhonePasswordResetRequest,
)
from app.services.auth_service import login_user, login_user_with_phone_otp, refresh_auth_token, reset_password_with_phone_otp, user_public
from app.services.customer_auth_service import get_customer_profile, register_customer, update_customer_profile
from app.services.otp_service import mark_user_phone_verified, request_phone_otp, verify_phone_otp

router = APIRouter(prefix="/customer/auth", tags=["customer-auth"])


@router.post("/register")
async def register(payload: CustomerRegisterRequest):
    data = await register_customer(payload)
    return success_response("Customer registered successfully.", data)


@router.post("/register/phone")
async def register_with_phone_otp(payload: PhoneCustomerRegisterRequest):
    otp = await verify_phone_otp(
        phone=payload.phone,
        code=payload.code,
        account_type="customer",
        purpose="register",
        consume=True,
    )
    data = await register_customer(payload)
    await mark_user_phone_verified(data["user"]["id"], otp["phone"])
    data["user"]["isPhoneVerified"] = True
    data["otp"] = otp
    return success_response("Customer registered and phone verified successfully.", data)


@router.post("/login")
async def login(payload: LoginRequest):
    data = await login_user(payload.email, payload.password, expected_account_type="customer")
    return success_response("Logged in successfully.", data)


@router.post("/login/phone")
async def login_with_phone_otp(payload: PhoneOtpLoginRequest):
    data = await login_user_with_phone_otp(payload.phone, payload.code, expected_account_type="customer")
    return success_response("Logged in with phone OTP successfully.", data)


@router.post("/otp/request")
async def request_otp(payload: PhoneOtpRequest):
    data = await request_phone_otp(
        phone=payload.phone,
        account_type="customer",
        purpose=payload.purpose,
        channel=payload.channel,
    )
    return success_response("OTP sent successfully.", data)


@router.post("/otp/verify")
async def verify_otp(payload: PhoneOtpVerifyRequest):
    data = await verify_phone_otp(
        phone=payload.phone,
        code=payload.code,
        account_type="customer",
        purpose=payload.purpose,
        consume=False,
    )
    return success_response("OTP verified successfully.", data)


@router.post("/password/phone/request")
async def request_phone_password_reset(payload: PhoneOtpRequest):
    data = await request_phone_otp(
        phone=payload.phone,
        account_type="customer",
        purpose="password_reset",
        channel=payload.channel,
    )
    return success_response("Password reset OTP sent successfully.", data)


@router.post("/password/phone/reset")
async def reset_phone_password(payload: PhonePasswordResetRequest):
    data = await reset_password_with_phone_otp(
        payload.phone,
        payload.code,
        payload.newPassword,
        expected_account_type="customer",
    )
    return success_response("Password reset successfully.", data)


@router.post("/refresh")
async def refresh(payload: RefreshTokenRequest):
    data = await refresh_auth_token(payload.refreshToken)
    return success_response("Token refreshed successfully.", data)


@router.post("/logout")
async def logout():
    return success_response("Logged out successfully.")


@router.get("/me")
async def me(current_user: dict = Depends(get_current_customer_user)):
    profile = await get_customer_profile(str(current_user["_id"]))
    return success_response(
        "Authenticated customer fetched successfully.",
        {"user": user_public(current_user), "profile": profile},
    )


@router.put("/profile")
async def update_profile(payload: CustomerProfileUpdateRequest, current_user: dict = Depends(get_current_customer_user)):
    profile = await update_customer_profile(str(current_user["_id"]), payload)
    return success_response("Customer profile updated successfully.", profile)


@router.post("/me/phone/request")
async def request_current_phone_verification(payload: PhoneOtpRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await request_phone_otp(
        phone=payload.phone or current_user.get("phone", ""),
        account_type="customer",
        purpose="verify_phone",
        channel=payload.channel,
    )
    return success_response("Phone verification OTP sent successfully.", data)


@router.post("/me/phone/verify")
async def verify_current_phone(payload: PhoneOtpVerifyRequest, current_user: dict = Depends(get_current_customer_user)):
    data = await verify_phone_otp(
        phone=payload.phone,
        code=payload.code,
        account_type="customer",
        purpose="verify_phone",
        consume=True,
    )
    await mark_user_phone_verified(current_user["_id"], data["phone"])
    refreshed = dict(current_user)
    refreshed["phone"] = data["phone"]
    refreshed["isPhoneVerified"] = True
    return success_response("Phone verified successfully.", {"otp": data, "user": user_public(refreshed)})
