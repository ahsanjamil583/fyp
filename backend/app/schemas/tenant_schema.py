from pydantic import BaseModel, Field


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    businessCategoryId: str | None = None
    description: str = ""
    contact: dict = Field(default_factory=dict)
    address: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)


class TenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    businessCategoryId: str | None = None
    description: str | None = None
    contact: dict | None = None
    address: dict | None = None
    settings: dict | None = None
    websiteSettings: dict | None = None
