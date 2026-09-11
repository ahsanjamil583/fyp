from pydantic import BaseModel, EmailStr, Field


class PhoneOtpRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    purpose: str = Field(default="login", pattern="^(login|register|verify_phone|password_reset)$")
    channel: str = Field(default="sms", pattern="^(sms|whatsapp|mock)$")


class PhoneOtpVerifyRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    code: str = Field(min_length=4, max_length=12)
    purpose: str = Field(default="login", pattern="^(login|register|verify_phone|password_reset)$")


class PhonePasswordResetRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    code: str = Field(min_length=4, max_length=12)
    newPassword: str = Field(min_length=6, max_length=128)


class PhoneBusinessRegisterRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    code: str = Field(min_length=4, max_length=12)
    password: str = Field(min_length=6, max_length=128)
    email: EmailStr | None = None


class EmailOtpRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(default="register", pattern="^(register|password_reset)$")


class EmailOtpVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    purpose: str = Field(default="register", pattern="^(register|password_reset)$")


class EmailPasswordResetRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    newPassword: str = Field(min_length=6, max_length=128)

