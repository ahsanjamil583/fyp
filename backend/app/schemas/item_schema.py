from pydantic import BaseModel, Field


class ItemCategoryCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    parentCategoryId: str | None = None
    isActive: bool = True


class ItemCategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    parentCategoryId: str | None = None
    isActive: bool | None = None


class StockRequest(BaseModel):
    quantity: float = 0
    lowStockThreshold: float = 0
    reservedQuantity: float = 0


class ImageMetadataRequest(BaseModel):
    provider: str = "local"
    fileId: str
    url: str


class ServiceDetailsRequest(BaseModel):
    durationMinutes: int = Field(default=0, ge=0, le=1440)
    bufferMinutes: int = Field(default=0, ge=0, le=480)
    deliveryMode: str = "onsite"


class ItemVariantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sku: str = ""
    price: float = Field(default=0, ge=0)
    compareAtPrice: float | None = Field(default=None, ge=0)
    stockQuantity: float = 0
    lowStockThreshold: float = 0
    isDefault: bool = False
    isActive: bool = True
    optionValues: dict = Field(default_factory=dict)


class BundleComponentRequest(BaseModel):
    itemId: str
    quantity: float = Field(default=1, gt=0)
    isOptional: bool = False
    notes: str = ""


class ItemCreateRequest(BaseModel):
    itemType: str = "product"
    name: str = Field(min_length=2, max_length=160)
    description: str = ""
    categoryId: str | None = None
    sku: str = ""
    price: float = Field(default=0, ge=0)
    costPrice: float = Field(default=0, ge=0)
    currency: str = "PKR"
    unit: str = "piece"
    images: list[ImageMetadataRequest] = Field(default_factory=list)
    status: str = "active"
    isSellable: bool = True
    isBookable: bool = False
    isStockTracked: bool = True
    stock: StockRequest = Field(default_factory=StockRequest)
    serviceDetails: ServiceDetailsRequest = Field(default_factory=ServiceDetailsRequest)
    variants: list[ItemVariantRequest] = Field(default_factory=list)
    bundleComponents: list[BundleComponentRequest] = Field(default_factory=list)
    customFields: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ItemUpdateRequest(BaseModel):
    itemType: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = None
    categoryId: str | None = None
    sku: str | None = None
    price: float | None = Field(default=None, ge=0)
    costPrice: float | None = Field(default=None, ge=0)
    currency: str | None = None
    unit: str | None = None
    images: list[ImageMetadataRequest] | None = None
    status: str | None = None
    isSellable: bool | None = None
    isBookable: bool | None = None
    isStockTracked: bool | None = None
    stock: StockRequest | None = None
    serviceDetails: ServiceDetailsRequest | None = None
    variants: list[ItemVariantRequest] | None = None
    bundleComponents: list[BundleComponentRequest] | None = None
    customFields: dict | None = None
    tags: list[str] | None = None
