from typing import Any

from pydantic import BaseModel, Field, field_validator

ALLOWED_FIELD_TYPES = {"text", "number", "date", "boolean", "select", "multi_select", "file", "reference"}
ALLOWED_MODULE_CODES = {"customers", "items", "transactions"}
ALLOWED_ENTITY_TYPES = {"customer", "item", "transaction"}


class CustomFieldCreateRequest(BaseModel):
    moduleCode: str
    entityType: str
    key: str = Field(min_length=2, max_length=60)
    label: str = Field(min_length=2, max_length=120)
    type: str
    required: bool = False
    options: list[str] = Field(default_factory=list)
    defaultValue: Any = None
    validation: dict = Field(default_factory=dict)
    showInTable: bool = True
    showInForm: bool = True
    order: int = 1
    isActive: bool = True

    @field_validator("moduleCode")
    @classmethod
    def validate_module_code(cls, value):
        if value not in ALLOWED_MODULE_CODES:
            raise ValueError("moduleCode must be customers, items, or transactions.")
        return value

    @field_validator("entityType")
    @classmethod
    def validate_entity_type(cls, value):
        if value not in ALLOWED_ENTITY_TYPES:
            raise ValueError("entityType must be customer, item, or transaction.")
        return value

    @field_validator("type")
    @classmethod
    def validate_type(cls, value):
        if value not in ALLOWED_FIELD_TYPES:
            raise ValueError("Invalid custom field type.")
        return value

    @field_validator("key")
    @classmethod
    def validate_key(cls, value):
        if not value.replace("_", "").isalnum() or value[0].isdigit():
            raise ValueError("Key must use letters, numbers, and underscores, and cannot start with a number.")
        return value


class CustomFieldUpdateRequest(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=120)
    required: bool | None = None
    options: list[str] | None = None
    defaultValue: Any = None
    validation: dict | None = None
    showInTable: bool | None = None
    showInForm: bool | None = None
    order: int | None = None
    isActive: bool | None = None


class CustomValuesValidationRequest(BaseModel):
    moduleCode: str
    entityType: str
    values: dict = Field(default_factory=dict)
