"""Request contracts for the cashier module.

Three audiences share this file: the owner managing cashier accounts, the cashier
creating in-store orders, and the owner importing historical order sheets. They are kept
together because they describe one module, and apart from the transaction schemas because
none of them may be reached by the customer-facing order routes.
"""

from pydantic import BaseModel, Field


# ------------------------------------------------------------- owner: cashiers --


class CashierPermissionsRequest(BaseModel):
    canViewAllCashierOrders: bool = False
    canAddCustomItems: bool = True
    canApplyDiscount: bool = True


class CashierCreateRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=120)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=30)
    employeeCode: str = Field(default="", max_length=40)
    password: str = Field(min_length=8, max_length=128)
    permissions: CashierPermissionsRequest = Field(default_factory=CashierPermissionsRequest)


class CashierUpdateRequest(BaseModel):
    fullName: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=200)
    employeeCode: str | None = Field(default=None, max_length=40)
    permissions: CashierPermissionsRequest | None = None


class CashierStatusRequest(BaseModel):
    isActive: bool


class CashierPasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    mustChangeOnNextLogin: bool = False


# --------------------------------------------------------- cashier: order entry --


class CashierOrderItemRequest(BaseModel):
    """One receipt line.

    ``itemId`` points at the tenant catalog. When it is empty the line is a manual entry,
    which needs its own name and price and never touches inventory.
    """

    itemId: str = ""
    name: str = Field(default="", max_length=200)
    quantity: int = Field(default=1, ge=1, le=999)
    unitPrice: float | None = Field(default=None, ge=0)
    selectedVariantIndex: int | None = None
    selectedVariantName: str = Field(default="", max_length=120)
    selectedOptions: dict = Field(default_factory=dict)
    variantSku: str = Field(default="", max_length=80)


class CashierOrderCreateRequest(BaseModel):
    customerName: str = Field(default="", max_length=120)
    customerPhone: str = Field(default="", max_length=30)
    customerEmail: str = Field(default="", max_length=200)
    items: list[CashierOrderItemRequest] = Field(default_factory=list)

    discountType: str = Field(default="amount")
    discountValue: float = Field(default=0, ge=0)
    taxType: str = Field(default="amount")
    taxValue: float = Field(default=0, ge=0)
    serviceCharge: float = Field(default=0, ge=0)
    deliveryFee: float = Field(default=0, ge=0)

    serviceType: str = Field(default="in_store")
    address: dict = Field(default_factory=dict)
    paymentMethod: str = Field(default="cash")
    amountReceived: float | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=1000)
    customFields: dict = Field(default_factory=dict)


# ----------------------------------------------------------- owner: sheet import --


class ImportRowItemPayload(BaseModel):
    name: str = Field(default="", max_length=200)
    sku: str = Field(default="", max_length=80)
    quantity: float = Field(default=1, ge=0)
    unitPrice: float = Field(default=0, ge=0)


class ImportRowPayload(BaseModel):
    rowNumber: int = 0
    orderNumber: str = Field(default="", max_length=80)
    orderDate: str = Field(default="", max_length=60)
    customerName: str = Field(default="", max_length=120)
    customerPhone: str = Field(default="", max_length=30)
    customerEmail: str = Field(default="", max_length=200)
    items: list[ImportRowItemPayload] = Field(default_factory=list)
    discount: float = 0
    tax: float = 0
    totalAmount: float = 0
    paymentMethod: str = Field(default="", max_length=40)
    paymentStatus: str = Field(default="", max_length=40)
    orderStatus: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=1000)


class OrderImportConfirmRequest(BaseModel):
    fileName: str = Field(default="imported-orders", max_length=255)
    rows: list[ImportRowPayload] = Field(default_factory=list)
    skipDuplicates: bool = True
