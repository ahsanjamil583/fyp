from pydantic import BaseModel, Field


class WhatsAppSettingsRequest(BaseModel):
    provider: str = Field(default="mock", pattern="^(mock|baileys)$")
    businessWhatsAppNumber: str = Field(min_length=6, max_length=32)
    displayName: str = Field(default="", max_length=120)
    agentEnabled: bool = True
    autoReplyEnabled: bool = True
    handoffEnabled: bool = True
    handoffKeywords: list[str] = Field(
        default_factory=lambda: ["human", "agent", "admin", "owner", "representative", "call me", "insan", "baat karni"]
    )
    welcomeMessage: str = Field(
        default="Assalam o Alaikum! Main BizXus AI assistant hoon. Aap products, prices, timing ya order ke bare mein pooch sakte hain.",
        max_length=500,
    )
    fallbackReply: str = Field(
        default="Sorry, main is waqt WhatsApp reply complete nahi kar pa raha. Business owner ko notify kar diya gaya hai.",
        max_length=500,
    )
    businessHoursMode: str = Field(default="always_on", pattern="^(always_on|business_hours|offline_handoff)$")


class WhatsAppMockInboundRequest(BaseModel):
    customerPhone: str = Field(min_length=6, max_length=32)
    customerName: str = Field(default="WhatsApp Customer", max_length=120)
    messageText: str = Field(min_length=1, max_length=1000)
    providerMessageId: str = Field(default="", max_length=180)


class WhatsAppOutboundRequest(BaseModel):
    toPhone: str = Field(min_length=6, max_length=32)
    messageText: str = Field(min_length=1, max_length=1000)


class WhatsAppBridgeInboundRequest(BaseModel):
    tenantId: str = Field(min_length=1, max_length=80)
    connectedNumber: str = Field(default="", max_length=32)
    customerPhone: str = Field(min_length=3, max_length=64)
    customerName: str = Field(default="WhatsApp Customer", max_length=120)
    messageText: str = Field(min_length=1, max_length=4000)
    providerMessageId: str = Field(default="", max_length=180)
    rawPayload: dict = Field(default_factory=dict)


class WhatsAppBridgeStatusRequest(BaseModel):
    tenantId: str = Field(min_length=1, max_length=80)
    status: str = Field(default="unknown", max_length=80)
    connectedNumber: str = Field(default="", max_length=32)
    lastError: str = Field(default="", max_length=500)


class WhatsAppDeliveryAck(BaseModel):
    deliveryStatus: str = Field(pattern="^(sent|failed)$")
