from pydantic import BaseModel, Field


class ModuleCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    category: str = "core"
    isActive: bool = True
    dependencies: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    configSchema: dict = Field(default_factory=dict)
    frontendRoutes: list[str] = Field(default_factory=list)
    apiPrefix: str = ""
    aiTools: list[str] = Field(default_factory=list)
    availability: dict = Field(default_factory=dict)
    usageLimits: dict = Field(default_factory=dict)


class TenantModuleConfigRequest(BaseModel):
    config: dict = Field(default_factory=dict)
