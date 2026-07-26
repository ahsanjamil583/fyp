from pydantic import BaseModel, Field, field_validator


ALLOWED_AGENT_PREVIEW_CHANNELS = {"owner_preview", "customer_portal", "website", "whatsapp"}


class AgentPreviewRequest(BaseModel):
    messageText: str = Field(min_length=1, max_length=2000)
    channel: str = Field(default="owner_preview", max_length=40)
    includeRecentMessages: bool = False

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        normalized = str(value or "owner_preview").strip().lower()
        if normalized not in ALLOWED_AGENT_PREVIEW_CHANNELS:
            raise ValueError("channel must be owner_preview, customer_portal, website, or whatsapp")
        return normalized
