from pydantic import BaseModel, EmailStr, Field

from app.core.password_policy import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH


class CustomerRegisterRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class CustomerProfileUpdateRequest(BaseModel):
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    defaultAddress: dict = Field(default_factory=dict)
    savedAddresses: list[dict] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
