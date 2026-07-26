from pydantic import BaseModel, EmailStr, Field


class CustomerCreateRequest(BaseModel):
    customerUserId: str | None = None
    type: str = "customer"
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    email: EmailStr | str = ""
    address: dict = Field(default_factory=dict)
    status: str = "active"
    tags: list[str] = Field(default_factory=list)
    customFields: dict = Field(default_factory=dict)


class CustomerUpdateRequest(BaseModel):
    customerUserId: str | None = None
    type: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    email: EmailStr | str | None = None
    address: dict | None = None
    status: str | None = None
    tags: list[str] | None = None
    customFields: dict | None = None
