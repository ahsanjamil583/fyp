from pydantic import BaseModel, EmailStr, Field

from app.core.password_policy import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH


class BusinessRegisterRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    email: EmailStr | None = None


class EmailBusinessRegisterRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    businessName: str | None = Field(default=None, max_length=160)


class LoginRequest(BaseModel):
    email: EmailStr | None = None
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class PasswordChangeRequest(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    newPassword: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class RefreshTokenRequest(BaseModel):
    refreshToken: str


class UserPublic(BaseModel):
    id: str
    fullName: str
    email: EmailStr | None = None
    phone: str
    accountType: str
    globalRole: str
    status: str
    isEmailVerified: bool
    isPhoneVerified: bool


class AuthResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "bearer"
    user: UserPublic
