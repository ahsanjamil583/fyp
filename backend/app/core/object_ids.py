from bson import ObjectId
from fastapi import HTTPException, status


def parse_object_id(value: str, label: str = "id") -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {label}.")
    return ObjectId(value)


def serialize_document(document: dict | None) -> dict | None:
    if document is None:
        return None

    serialized = {}
    for key, value in document.items():
        if isinstance(value, ObjectId):
            serialized["id" if key == "_id" else key] = str(value)
        elif isinstance(value, list):
            serialized[key] = [serialize_document(item) if isinstance(item, dict) else item for item in value]
        elif isinstance(value, dict):
            serialized[key] = serialize_document(value)
        elif hasattr(value, "isoformat"):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized
