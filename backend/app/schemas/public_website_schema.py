from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PublicOrderItemRequest(BaseModel):
    # Orders are built from the cart or the named draft lines. Silently dropping an
    # unknown field would let a client believe it ordered something it did not.
    model_config = ConfigDict(extra="forbid")

    itemId: str
    quantity: int = Field(default=1, ge=1, le=99)
    selectedVariantIndex: int | None = None
    selectedVariantName: str = ""
    selectedOptions: dict = Field(default_factory=dict)
    variantSku: str = ""


class PublicOrderRequest(BaseModel):
    # Orders are built from the cart or the named draft lines. Silently dropping an
    # unknown field would let a client believe it ordered something it did not.
    model_config = ConfigDict(extra="forbid")

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
