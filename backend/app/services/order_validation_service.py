from fastapi import HTTPException, status


ALLOWED_FULFILLMENT_TYPES = {"none", "pickup", "delivery"}


def normalize_notes(notes: str | None) -> str:
    return str(notes or "").strip()[:1000]


def normalize_fulfillment(fulfillment: dict | None) -> dict:
    payload = fulfillment or {}
    fulfillment_type = str(payload.get("type") or "none").strip().lower()
    if fulfillment_type not in ALLOWED_FULFILLMENT_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid fulfillment type.")

    address = payload.get("address") or {}
    normalized_address = {
        "line1": str(address.get("line1") or address.get("addressLine1") or address.get("street") or "").strip(),
        "city": str(address.get("city") or address.get("addressCity") or "").strip(),
    }

    if fulfillment_type == "delivery" and (not normalized_address["line1"] or not normalized_address["city"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Delivery orders require address line and city.",
        )

    if fulfillment_type != "delivery":
        normalized_address = {}

    return {
        "type": fulfillment_type,
        "address": normalized_address,
    }
