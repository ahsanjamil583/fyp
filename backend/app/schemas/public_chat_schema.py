from pydantic import BaseModel, Field


class PublicChatMessageRequest(BaseModel):
    messageText: str = Field(min_length=2, max_length=1000)
    conversationId: str | None = None
