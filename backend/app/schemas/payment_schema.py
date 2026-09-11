from pydantic import BaseModel, Field


class PaymentSettingsRequest(BaseModel):
    codEnabled: bool = True
    manualEnabled: bool = True
    jazzCashEnabled: bool = False
    easyPaisaEnabled: bool = False
    bankTransferEnabled: bool = True
    stripeEnabled: bool = False
    paymentsDemoMode: bool = True
    requireOwnerApproval: bool = True
    bankName: str = Field(default="", max_length=120)
    jazzCashNumber: str = Field(default="", max_length=40)
    jazzCashAccountTitle: str = Field(default="", max_length=120)
    easyPaisaNumber: str = Field(default="", max_length=40)
    easyPaisaAccountTitle: str = Field(default="", max_length=120)
    bankAccountTitle: str = Field(default="", max_length=120)
    bankAccountNumber: str = Field(default="", max_length=80)
    bankIban: str = Field(default="", max_length=80)
    defaultMethod: str = "cod"
    customerInstructions: str = Field(default="", max_length=1000)


class StripeCheckoutSessionRequest(BaseModel):
    successUrl: str = Field(default="", max_length=500)
    cancelUrl: str = Field(default="", max_length=500)


class GatewayCheckoutRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32)


class StripePaymentSyncRequest(BaseModel):
    sessionId: str = Field(default="", max_length=200)


class PaymentRecordRequest(BaseModel):
    amount: float = Field(gt=0)
    method: str = "cod"
    status: str = "paid"
    referenceNumber: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=1000)
    screenshotUrl: str = Field(default="", max_length=500)


class PaymentRefundRequest(BaseModel):
    amount: float = Field(gt=0)
    method: str = "manual"
    referenceNumber: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=1000)


class PaymentVerificationDecisionRequest(BaseModel):
    decision: str = "approve"
    notes: str = Field(default="", max_length=1000)
