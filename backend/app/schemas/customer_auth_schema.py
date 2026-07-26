from pydantic import BaseModel, EmailStr, Field


class CustomerRegisterRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=6, max_length=128)
    email: EmailStr | None = None


class CustomerProfileUpdateRequest(BaseModel):
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    defaultAddress: dict = Field(default_factory=dict)
    savedAddresses: list[dict] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)
