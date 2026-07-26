from pydantic import BaseModel, Field


class OwnerAgentChatRequest(BaseModel):
    messageText: str = Field(min_length=1, max_length=2000)
    includeHistory: bool = True


class OwnerAgentHistoryQuery(BaseModel):
    limit: int = 30
