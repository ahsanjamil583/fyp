from fastapi import HTTPException, status


ALLOWED_TRANSACTION_TYPES = {"order", "quote_request", "booking_request", "inquiry"}
ORDER_TRANSACTION_TYPES = {"order"}

TRANSACTION_TYPE_PREFIXES = {
    "order": "ORD",
    "quote_request": "QTE",
    "booking_request": "BKG",
    "inquiry": "INQ",
}

INITIAL_TRANSACTION_STATUSES = {
    "order": "pending",
    "quote_request": "requested",
    "booking_request": "requested",
    "inquiry": "open",
}

INITIAL_PAYMENT_STATUSES = {
    "order": "unpaid",
    "quote_request": "awaiting_quote",
    "booking_request": "unpaid",
    "inquiry": "not_applicable",
}

TRANSACTION_STATUS_OPTIONS = {
    "order": ["pending", "confirmed", "processing", "ready", "completed", "cancelled"],
    "quote_request": ["requested", "quoted", "approved", "rejected", "cancelled"],
    "booking_request": ["requested", "confirmed", "completed", "cancelled"],
    "inquiry": ["open", "responded", "closed", "cancelled"],
}

PAYMENT_STATUS_OPTIONS = {
    "order": ["unpaid", "cod", "pending_verification", "partially_paid", "paid", "rejected", "refunded"],
    "quote_request": ["awaiting_quote", "quoted", "paid", "not_applicable"],
    "booking_request": ["unpaid", "cod", "pending_verification", "partially_paid", "paid", "rejected", "refunded"],
    "inquiry": ["not_applicable"],
}


def normalize_transaction_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized or normalized == "auto":
        return None
    if normalized not in ALLOWED_TRANSACTION_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid transaction type.")
    return normalized


def infer_transaction_type(requested_type: str | None, items: list[dict]) -> str:
    if requested_type:
        validate_transaction_type_for_items(requested_type, items)
        return requested_type
    if not items:
        return "inquiry"
    if all(_is_booking_eligible_item(item) for item in items):
        return "booking_request"
    return "order"


def validate_transaction_type_for_items(transaction_type: str, items: list[dict]) -> None:
    if transaction_type == "inquiry":
        return
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one item is required for this transaction type.")
    if transaction_type == "booking_request" and not all(_is_booking_eligible_item(item) for item in items):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Booking requests are only supported for services or bookable items.",
        )


def get_initial_transaction_status(transaction_type: str) -> str:
    return INITIAL_TRANSACTION_STATUSES[transaction_type]


def get_initial_payment_status(transaction_type: str) -> str:
    return INITIAL_PAYMENT_STATUSES[transaction_type]


def get_allowed_statuses(transaction_type: str) -> list[str]:
    return TRANSACTION_STATUS_OPTIONS.get(transaction_type, ["pending"])


def get_allowed_payment_statuses(transaction_type: str) -> list[str]:
    return PAYMENT_STATUS_OPTIONS.get(transaction_type, ["unpaid"])


def validate_transaction_status(transaction_type: str, status_value: str) -> str:
    normalized = str(status_value or "").strip().lower()
    if normalized not in get_allowed_statuses(transaction_type):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid transaction status.")
    return normalized


def validate_payment_status(transaction_type: str, status_value: str) -> str:
    normalized = str(status_value or "").strip().lower()
    if normalized not in get_allowed_payment_statuses(transaction_type):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid payment status.")
    return normalized


def is_revenue_transaction(transaction: dict) -> bool:
    return transaction.get("transactionType") in ORDER_TRANSACTION_TYPES and transaction.get("status") != "cancelled"


def _is_booking_eligible_item(item: dict) -> bool:
    return bool(item.get("isBookable")) or item.get("itemType") in {"service", "bookable"}
