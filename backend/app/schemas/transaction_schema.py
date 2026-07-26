from pydantic import BaseModel, Field


class TransactionUpdateRequest(BaseModel):
    status: str | None = None
    paymentStatus: str | None = None
    internalNotes: str = Field(default="", max_length=1000)
