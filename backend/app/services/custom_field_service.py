from datetime import datetime, timezone
import re

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.core.permissions import get_owned_tenant_or_403
from app.db.mongodb import get_database

SUPPORTED_FIELD_TYPES = {"text", "number", "date", "boolean", "select", "multi_select", "file", "reference"}
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_field_options(options: list[str] | None) -> list[str]:
    normalized = []
    seen = set()
    for option in options or []:
        clean = str(option).strip()
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(clean)
    return normalized


def _normalize_validation(validation: dict | None) -> dict:
    normalized = dict(validation or {})
    for key in ["minLength", "maxLength", "min", "max"]:
        if normalized.get(key) in ("", None):
            normalized.pop(key, None)
    return normalized


def _validate_value_against_field(field: dict, value, *, key_override: str | None = None, enforce_required: bool = True) -> list[dict]:
    key = key_override or field["key"]
    errors = []
    is_empty = value is None or value == "" or value == []

    if enforce_required and field.get("required") and is_empty:
        return [{"key": key, "message": f"{field['label']} is required."}]

    if is_empty:
        return []

    field_type = field["type"]
    validation = field.get("validation", {}) or {}
    if field_type == "text":
        if not isinstance(value, str):
            errors.append({"key": key, "message": f"{field['label']} must be text."})
        else:
            min_len = validation.get("minLength")
            max_len = validation.get("maxLength")
            if min_len is not None and len(value) < int(min_len):
                errors.append({"key": key, "message": f"{field['label']} is too short."})
            if max_len is not None and len(value) > int(max_len):
                errors.append({"key": key, "message": f"{field['label']} is too long."})
    elif field_type == "number":
        if not isinstance(value, int | float):
            errors.append({"key": key, "message": f"{field['label']} must be a number."})
        else:
            minimum = validation.get("min")
            maximum = validation.get("max")
            if minimum is not None and value < float(minimum):
                errors.append({"key": key, "message": f"{field['label']} is below minimum."})
            if maximum is not None and value > float(maximum):
                errors.append({"key": key, "message": f"{field['label']} is above maximum."})
    elif field_type == "boolean":
        if not isinstance(value, bool):
            errors.append({"key": key, "message": f"{field['label']} must be true or false."})
    elif field_type == "select":
        if value not in field.get("options", []):
            errors.append({"key": key, "message": f"{field['label']} must be one of the allowed options."})
    elif field_type == "multi_select":
        if not isinstance(value, list) or any(option not in field.get("options", []) for option in value):
            errors.append({"key": key, "message": f"{field['label']} contains invalid options."})
    elif field_type == "date":
        if not isinstance(value, str) or not DATE_PATTERN.match(value):
            errors.append({"key": key, "message": f"{field['label']} must use YYYY-MM-DD format."})
    elif field_type == "file":
        if not isinstance(value, str | dict):
            errors.append({"key": key, "message": f"{field['label']} must be a file path or file object."})
    elif field_type == "reference":
        if not isinstance(value, str | dict):
            errors.append({"key": key, "message": f"{field['label']} must be a reference code or object."})

    return errors


def _validate_field_definition_payload(field: dict) -> None:
    if field["type"] not in SUPPORTED_FIELD_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported custom field type.")

    if field["type"] in {"select", "multi_select"} and not field.get("options"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select fields require options.")

    validation = field.get("validation", {}) or {}
    if field["type"] == "text":
        min_len = validation.get("minLength")
        max_len = validation.get("maxLength")
        if min_len is not None and max_len is not None and int(min_len) > int(max_len):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Text field minLength cannot exceed maxLength.")
    if field["type"] == "number":
        minimum = validation.get("min")
        maximum = validation.get("max")
        if minimum is not None and maximum is not None and float(minimum) > float(maximum):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Number field min cannot exceed max.")

    default_errors = _validate_value_against_field(field, field.get("defaultValue"), key_override="defaultValue", enforce_required=False)
    if default_errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=default_errors[0]["message"])


async def list_custom_fields(tenant_id: str, user: dict, module_code: str | None = None, entity_type: str | None = None) -> list[dict]:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)

    query = {"tenantId": tenant_oid}
    if module_code:
        query["moduleCode"] = module_code
    if entity_type:
        query["entityType"] = entity_type

    cursor = db.custom_field_definitions.find(query).sort([("order", 1), ("createdAt", 1)])
    return [serialize_document(field) async for field in cursor]


async def _list_custom_fields_for_tenant_oid(tenant_oid: ObjectId, module_code: str | None = None, entity_type: str | None = None) -> list[dict]:
    db = get_database()
    query = {"tenantId": tenant_oid}
    if module_code:
        query["moduleCode"] = module_code
    if entity_type:
        query["entityType"] = entity_type
    cursor = db.custom_field_definitions.find(query).sort([("order", 1), ("createdAt", 1)])
    return [serialize_document(field) async for field in cursor]


async def create_custom_field(tenant_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)

    existing = await db.custom_field_definitions.find_one(
        {
            "tenantId": tenant_oid,
            "moduleCode": payload.moduleCode,
            "entityType": payload.entityType,
            "key": payload.key,
        }
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Custom field key already exists for this entity.")

    now = datetime.now(timezone.utc)
    field = {
        "tenantId": tenant_oid,
        "moduleCode": payload.moduleCode,
        "entityType": payload.entityType,
        "key": payload.key,
        "label": payload.label,
        "type": payload.type,
        "required": payload.required,
        "options": _normalize_field_options(payload.options),
        "defaultValue": payload.defaultValue,
        "validation": _normalize_validation(payload.validation),
        "showInTable": payload.showInTable,
        "showInForm": payload.showInForm,
        "order": payload.order,
        "isActive": payload.isActive,
        "createdAt": now,
        "updatedAt": now,
    }
    _validate_field_definition_payload(field)
    field["_id"] = (await db.custom_field_definitions.insert_one(field)).inserted_id
    return serialize_document(field)


async def update_custom_field(tenant_id: str, field_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    field_oid = parse_object_id(field_id, "fieldId")
    await get_owned_tenant_or_403(tenant_oid, user)

    existing = await db.custom_field_definitions.find_one({"_id": field_oid, "tenantId": tenant_oid})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom field not found.")

    update = {"updatedAt": datetime.now(timezone.utc)}
    fields_set = payload.model_fields_set
    for key in ["label", "required", "showInTable", "showInForm", "order", "isActive"]:
        if key in fields_set:
            update[key] = getattr(payload, key)

    if "defaultValue" in fields_set:
        update["defaultValue"] = payload.defaultValue
    if "options" in fields_set:
        update["options"] = _normalize_field_options(payload.options)
    if "validation" in fields_set:
        update["validation"] = _normalize_validation(payload.validation)

    merged = {**existing, **update}
    _validate_field_definition_payload(merged)
    await db.custom_field_definitions.update_one({"_id": field_oid, "tenantId": tenant_oid}, {"$set": update})
    return serialize_document(await db.custom_field_definitions.find_one({"_id": field_oid, "tenantId": tenant_oid}))


async def delete_custom_field(tenant_id: str, field_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    field_oid = parse_object_id(field_id, "fieldId")
    await get_owned_tenant_or_403(tenant_oid, user)

    result = await db.custom_field_definitions.update_one(
        {"_id": field_oid, "tenantId": tenant_oid},
        {"$set": {"isActive": False, "updatedAt": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom field not found.")
    return serialize_document(await db.custom_field_definitions.find_one({"_id": field_oid, "tenantId": tenant_oid}))


async def validate_custom_values(tenant_id: str, module_code: str, entity_type: str, values: dict, user: dict) -> dict:
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)
    return await validate_custom_values_for_tenant_oid(tenant_oid, module_code, entity_type, values)


async def validate_custom_values_for_tenant_oid(tenant_oid: ObjectId, module_code: str, entity_type: str, values: dict) -> dict:
    fields = await _list_custom_fields_for_tenant_oid(tenant_oid, module_code, entity_type)
    active_fields = [field for field in fields if field.get("isActive")]
    errors = []
    normalized = {}

    for field in active_fields:
        key = field["key"]
        value = values.get(key, field.get("defaultValue"))
        errors.extend(_validate_value_against_field(field, value))
        normalized[key] = value

    return {"valid": len(errors) == 0, "errors": errors, "values": normalized}
