from pydantic import BaseModel, ConfigDict, Field


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
    # Orders are built from the cart or the named draft lines. Silently dropping an
    # unknown field would let a client believe it ordered something it did not.
    model_config = ConfigDict(extra="forbid")

    tenantId: str
    transactionType: str = "auto"
    paymentMethod: str | None = None
    fulfillment: dict = Field(default_factory=dict)
    notes: str = ""
    customFields: dict = Field(default_factory=dict)


class CustomerDraftConfirmRequest(BaseModel):
    # Orders are built from the cart or the named draft lines. Silently dropping an
    # unknown field would let a client believe it ordered something it did not.
    model_config = ConfigDict(extra="forbid")

    conversationId: str | None = None
    transactionType: str = "auto"
    paymentMethod: str | None = None
    items: list[dict] = Field(min_length=1)
    fulfillment: dict = Field(default_factory=dict)
    notes: str = ""
    customFields: dict = Field(default_factory=dict)


class CustomerChatMessageRequest(BaseModel):
    messageText: str = Field(min_length=2, max_length=1000)
