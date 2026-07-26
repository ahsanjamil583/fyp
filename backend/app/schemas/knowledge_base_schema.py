from pydantic import BaseModel, Field


class KnowledgeTextCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    content: str = Field(min_length=5, max_length=120000)
    moduleCode: str = "ai_chat"
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    isActive: bool = True


class KnowledgeDocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=180)
    content: str | None = Field(default=None, min_length=5, max_length=120000)
    moduleCode: str | None = None
    tags: list[str] | None = None
    metadata: dict | None = None
    isActive: bool | None = None


class KnowledgeBaseTestQuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    channel: str = "owner_preview"
