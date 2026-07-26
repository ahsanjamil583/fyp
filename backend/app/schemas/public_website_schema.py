from pydantic import BaseModel, EmailStr, Field


class PublicOrderItemRequest(BaseModel):
    itemId: str
    quantity: int = Field(default=1, ge=1, le=99)
    selectedVariantIndex: int | None = None
    selectedVariantName: str = ""
    selectedOptions: dict = Field(default_factory=dict)
    variantSku: str = ""


class PublicOrderRequest(BaseModel):
    customerName: str = Field(min_length=2, max_length=120)
    customerPhone: str = Field(min_length=7, max_length=30)
    customerEmail: EmailStr | str = ""
    transactionType: str = "auto"
    paymentMethod: str | None = None
    items: list[PublicOrderItemRequest] = Field(default_factory=list)
    fulfillment: dict = Field(default_factory=dict)
    notes: str = ""
    customFields: dict = Field(default_factory=dict)
    conversationId: str | None = None
