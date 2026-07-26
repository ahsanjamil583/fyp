from pydantic import BaseModel, Field


class CartItemCreateRequest(BaseModel):
    tenantId: str
    itemId: str
    quantity: int = Field(default=1, ge=1, le=99)


class FavoriteItemRequest(BaseModel):
    tenantId: str
    itemId: str


class CartItemUpdateRequest(BaseModel):
    quantity: int = Field(ge=1, le=99)


class CustomerOrderCreateRequest(BaseModel):
    tenantId: str
    transactionType: str = "auto"
    paymentMethod: str | None = None
    fulfillment: dict = Field(default_factory=dict)
    notes: str = ""
    customFields: dict = Field(default_factory=dict)


class CustomerDraftConfirmRequest(BaseModel):
    conversationId: str | None = None
    transactionType: str = "auto"
    paymentMethod: str | None = None
    items: list[dict] = Field(min_length=1)
    fulfillment: dict = Field(default_factory=dict)
    notes: str = ""
    customFields: dict = Field(default_factory=dict)


class CustomerChatMessageRequest(BaseModel):
    messageText: str = Field(min_length=2, max_length=1000)
