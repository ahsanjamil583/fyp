from fastapi import APIRouter, Depends, HTTPException, status

from app.core.responses import success_response
from app.core.security import get_authenticated_user, get_current_business_user, get_current_user
from app.schemas.auth_schema import (
    BusinessRegisterRequest,
    EmailBusinessRegisterRequest,
    LoginRequest,
    PasswordChangeRequest,
    RefreshTokenRequest,
)
from app.schemas.otp_schema import (
    EmailOtpRequest,
    EmailOtpVerifyRequest,
    EmailPasswordResetRequest,
    PhoneBusinessRegisterRequest,
    PhoneOtpRequest,
    PhoneOtpVerifyRequest,
    PhonePasswordResetRequest,
)
from app.services.auth_service import (
    auth_payload,
    change_password,
    login_user,
    refresh_auth_token,
    register_business_owner,
    register_business_owner_with_email_otp,
    reset_password_with_email_otp,
    reset_password_with_phone_otp,
    user_public,
)
from app.services.otp_service import mark_user_phone_verified, request_email_otp, request_phone_otp, verify_email_otp, verify_phone_otp

router = APIRouter(prefix="/auth", tags=["business-auth"])


@router.post("/register")
async def register(payload: BusinessRegisterRequest):
    data = await register_business_owner(payload)
    return success_response("Business owner registered successfully.", data)


@router.post("/register/phone")
async def register_with_phone_otp(payload: PhoneBusinessRegisterRequest):
    otp = await verify_phone_otp(
        phone=payload.phone,
        code=payload.code,
        account_type="business_owner",
        purpose="register",
        consume=True,
    )
    data = await register_business_owner(payload)
    await mark_user_phone_verified(data["user"]["id"], otp["phone"])
    data["user"]["isPhoneVerified"] = True
    data["otp"] = otp
    return success_response("Business owner registered and phone verified successfully.", data)


@router.post("/register/email")
async def register_with_email_otp(payload: EmailBusinessRegisterRequest):
    data = await register_business_owner_with_email_otp(payload)
    return success_response("Business owner registered and email verified successfully.", data)


@router.post("/login")
async def login(payload: LoginRequest):
    """Owners and cashiers share this form.

    The response says which kind of account signed in, and the client routes on that:
    an owner lands on the dashboard, a cashier on the cashier workspace. Every route on
    either side re-checks the account type server-side, so the redirect is convenience,
    not the control.
    """
    data = await login_user(payload.email, payload.password, expected_account_type={"business_owner", "cashier"})
    return success_response("Logged in successfully.", data)


@router.post("/otp/request")
async def request_otp(payload: PhoneOtpRequest):
    data = await request_phone_otp(
        phone=payload.phone,
        account_type="business_owner",
        purpose=payload.purpose,
        channel=payload.channel,
    )
    return success_response("OTP sent successfully.", data)


@router.post("/otp/verify")
async def verify_otp(payload: PhoneOtpVerifyRequest):
    data = await verify_phone_otp(
        phone=payload.phone,
        code=payload.code,
        account_type="business_owner",
        purpose=payload.purpose,
        consume=False,
    )
    return success_response("OTP verified successfully.", data)


@router.post("/otp/email/request")
async def request_email_verification_otp(payload: EmailOtpRequest):
    data = await request_email_otp(
        email=payload.email,
        account_type="business_owner",
        purpose=payload.purpose,
    )
    return success_response("Verification code sent successfully.", data)


@router.post("/otp/email/verify")
async def verify_email_verification_otp(payload: EmailOtpVerifyRequest):
    data = await verify_email_otp(
        email=payload.email,
        code=payload.code,
        account_type="business_owner",
        purpose=payload.purpose,
        consume=False,
    )
    return success_response("Verification code verified successfully.", data)


@router.post("/password/phone/request")
async def request_phone_password_reset(payload: PhoneOtpRequest):
    data = await request_phone_otp(
        phone=payload.phone,
        account_type="business_owner",
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
        expected_account_type="business_owner",
    )
    return success_response("Password reset successfully.", data)


@router.post("/password/email/request")
async def request_email_password_reset(payload: EmailOtpRequest):
    data = await request_email_otp(
        email=payload.email,
        account_type="business_owner",
        purpose="password_reset",
    )
    return success_response("Password reset code sent successfully.", data)


@router.post("/password/email/reset")
async def reset_email_password(payload: EmailPasswordResetRequest):
    data = await reset_password_with_email_otp(
        payload.email,
        payload.code,
        payload.newPassword,
        expected_account_type="business_owner",
    )
    return success_response("Password reset successfully.", data)


@router.post("/password/change")
async def change_business_password(
    payload: PasswordChangeRequest,
    current_user: dict = Depends(get_authenticated_user),
):
    """Depends on the ungated dependency so an account flagged for reset can escape it."""
    if current_user.get("accountType") not in {"business_owner", "cashier"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business account required.")
    data = await change_password(current_user, payload.currentPassword, payload.newPassword)
    return success_response("Password changed successfully.", data)


@router.post("/refresh")
async def refresh(payload: RefreshTokenRequest):
    data = await refresh_auth_token(payload.refreshToken)
    return success_response("Token refreshed successfully.", data)


@router.post("/logout")
async def logout():
    return success_response("Logged out successfully.")


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    """Identity for both workspaces.

    Cashiers restore their session through this endpoint too, so it accepts either
    account type and reports which one it is rather than rejecting the cashier.
    """
    if current_user.get("accountType") not in {"business_owner", "cashier"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business account required.")
    return success_response("Authenticated user fetched successfully.", user_public(current_user))


@router.post("/me/phone/request")
async def request_current_phone_verification(payload: PhoneOtpRequest, current_user: dict = Depends(get_current_business_user)):
    data = await request_phone_otp(
        phone=payload.phone or current_user.get("phone", ""),
        account_type="business_owner",
        purpose="verify_phone",
        channel=payload.channel,
    )
    return success_response("Phone verification OTP sent successfully.", data)


@router.post("/me/phone/verify")
async def verify_current_phone(payload: PhoneOtpVerifyRequest, current_user: dict = Depends(get_current_business_user)):
    data = await verify_phone_otp(
        phone=payload.phone,
        code=payload.code,
        account_type="business_owner",
        purpose="verify_phone",
        consume=True,
    )
    await mark_user_phone_verified(current_user["_id"], data["phone"])
    refreshed = dict(current_user)
    refreshed["phone"] = data["phone"]
    refreshed["isPhoneVerified"] = True
    return success_response("Phone verified successfully.", {"otp": data, "user": user_public(refreshed)})
