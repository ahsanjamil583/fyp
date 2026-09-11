from typing import Literal

from pydantic import BaseModel, Field


class AdminUserUpdateRequest(BaseModel):
    status: Literal["active", "suspended"] | None = None
    globalRole: Literal["user", "platform_admin"] | None = None
    isEmailVerified: bool | None = None
    isPhoneVerified: bool | None = None


class AdminTenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    businessCategoryId: str | None = None
    description: str | None = None
    contact: dict | None = None
    address: dict | None = None
    settings: dict | None = None
    websiteSettings: dict | None = None
    status: Literal["draft", "active", "archived"] | None = None
    websiteStatus: Literal["not_generated", "pending_review", "published", "unpublished", "rejected"] | None = None


class AdminPackageUpgradeDecisionRequest(BaseModel):
    status: Literal["approved", "rejected"]
    note: str | None = Field(default="", max_length=500)


class AdminWebsiteRequestDecisionRequest(BaseModel):
    status: Literal["approved", "rejected"]
    note: str | None = Field(default="", max_length=500)


class AdminModuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    category: str | None = None
    isActive: bool | None = None
    dependencies: list[str] | None = None
    permissions: list[str] | None = None
    configSchema: dict | None = None
    frontendRoutes: list[str] | None = None
    apiPrefix: str | None = None
    aiTools: list[str] | None = None
    availability: dict | None = None
    usageLimits: dict | None = None
