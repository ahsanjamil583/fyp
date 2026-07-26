from typing import Any

from pydantic import BaseModel, Field


class WhatsAppSettingsRequest(BaseModel):
    provider: str = Field(default="mock", pattern="^(mock|meta_cloud)$")
    businessWhatsAppNumber: str = Field(min_length=6, max_length=32)
    displayName: str = Field(default="", max_length=120)
    phoneNumberId: str = Field(default="", max_length=120)
    whatsappBusinessAccountId: str = Field(default="", max_length=120)
    accessToken: str = Field(default="", max_length=1000)
    apiVersion: str = Field(default="v21.0", max_length=20)
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


class WhatsAppEmbeddedSignupCaptureRequest(BaseModel):
    source: str = Field(default="fb_login", max_length=80)
    status: str = Field(default="", max_length=80)
    authorizationCode: str = Field(default="", max_length=2000)
    authResponse: dict[str, Any] = Field(default_factory=dict)
    embeddedSignup: dict[str, Any] = Field(default_factory=dict)
    callbackQuery: dict[str, Any] = Field(default_factory=dict)
    receivedAt: str = Field(default="", max_length=80)


class WhatsAppPhoneRegistrationRequest(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class WhatsAppWebhookRoutingTestRequest(BaseModel):
    customerPhone: str = Field(default="+923001234567", min_length=6, max_length=32)
    customerName: str = Field(default="Routing Test Customer", max_length=120)
    messageText: str = Field(default="Zinger burger available hai?", max_length=1000)
    phoneNumberId: str = Field(default="", max_length=120)
    providerMessageId: str = Field(default="", max_length=180)
    sendReply: bool = False


class WhatsAppLiveWebhookTestRequest(BaseModel):
    customerPhone: str = Field(default="+923001234567", min_length=6, max_length=32)
    customerName: str = Field(default="Live Test Customer", max_length=120)
    messageText: str = Field(default="Zinger burger available hai?", min_length=1, max_length=1000)
    providerMessageId: str = Field(default="", max_length=180)
    processWithAgent: bool = False


class WhatsAppGoLiveTestRunRequest(BaseModel):
    customerPhone: str = Field(default="+923001234567", min_length=6, max_length=32)
    customerName: str = Field(default="Live Test Customer", max_length=120)
    testMessage: str = Field(default="Zinger burger available hai?", min_length=1, max_length=1000)
    realCustomerMessageReceived: bool = False
    aiReplyDelivered: bool = False
    conversationVisible: bool = False
    orderFlowTested: bool = False
    orderCreated: bool = False
    handoffTested: bool = False
    ownerNotificationCreated: bool = False
    notes: str = Field(default="", max_length=1000)
    result: str = Field(default="auto", pattern="^(auto|passed|warning|failed)$")
