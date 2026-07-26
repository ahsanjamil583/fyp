from pydantic import BaseModel, Field


class ReportDeliverySettingsRequest(BaseModel):
    enabled: bool = True
    whatsappEnabled: bool = True
    smsEnabled: bool = False
    deliveryTime: str = Field(default="21:00", max_length=5)
    timezone: str = Field(default="Asia/Karachi", max_length=80)
    whatsappRecipient: str = Field(default="", max_length=40)
    smsRecipient: str = Field(default="", max_length=40)
    languageMode: str = Field(default="auto", max_length=20)
    includeLowStock: bool = True
    includeTopItems: bool = True
    includeRecentOrders: bool = True


class ReportDeliveryRequest(BaseModel):
    summaryDate: str | None = None
    channels: list[str] = Field(default_factory=lambda: ["whatsapp", "sms"])
    dryRun: bool = False


class ScheduledReportRunRequest(BaseModel):
    summaryDate: str | None = None
    dryRun: bool = False
