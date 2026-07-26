from pydantic import BaseModel, Field


class BusinessCategoryCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    slug: str | None = None
    description: str = ""
    icon: str = ""
    isActive: bool = True
    suggestedModules: list[str] = Field(default_factory=list)
    defaultCustomFields: list[dict] = Field(default_factory=list)
    aiHints: dict = Field(default_factory=dict)
    aiPromptFragments: list[str] = Field(default_factory=list)
    websiteHints: dict = Field(default_factory=dict)
    fulfillmentHints: dict = Field(default_factory=dict)
    analyticsSuggestions: list[str] = Field(default_factory=list)


class BusinessCategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    slug: str | None = None
    description: str | None = None
    icon: str | None = None
    isActive: bool | None = None
    suggestedModules: list[str] | None = None
    defaultCustomFields: list[dict] | None = None
    aiHints: dict | None = None
    aiPromptFragments: list[str] | None = None
    websiteHints: dict | None = None
    fulfillmentHints: dict | None = None
    analyticsSuggestions: list[str] | None = None
