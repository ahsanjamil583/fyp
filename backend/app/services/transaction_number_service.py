from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from app.db.mongodb import get_database
from app.services.transaction_workflow_service import TRANSACTION_TYPE_PREFIXES


async def generate_transaction_number(tenant_id: ObjectId, transaction_type: str) -> str:
    db = get_database()
    now = datetime.now(timezone.utc)
    date_key = now.strftime("%Y%m%d")
    prefix = TRANSACTION_TYPE_PREFIXES.get(transaction_type, "TRX")
    counter_id = f"tenant_transaction_seq:{tenant_id}:{transaction_type}:{date_key}"

    counter = await db.counters.find_one_and_update(
        {"_id": counter_id},
        {
            "$inc": {"value": 1},
            "$setOnInsert": {"tenantId": tenant_id, "transactionType": transaction_type, "dateKey": date_key, "createdAt": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    return f"{prefix}-{date_key}-{counter['value']:05d}"


async def generate_order_transaction_number(tenant_id: ObjectId) -> str:
    return await generate_transaction_number(tenant_id, "order")
