"""Explicit response contracts for public businesses and customer orders."""
from app.core.object_ids import serialize_document
from app.core.item_views import customer_stock_snapshot


def public_business_view(tenant: dict | None) -> dict:
    fields = {"_id", "id", "name", "slug", "description", "businessCategoryId", "logo", "coverImage", "contact", "address", "status", "websiteStatus", "websiteSettings", "enabledModuleCodes"}
    data = serialize_document({k: v for k, v in (tenant or {}).items() if k in fields})
    data["settings"] = {k: v for k, v in ((tenant or {}).get("settings") or {}).items() if k in {"currency", "languageMode", "timezone", "publicVisibility"}}
    return data


def customer_order_view(order: dict) -> dict:
    fields = {"_id", "id", "tenantId", "transactionNumber", "transactionType", "source", "status", "items", "pricing", "paymentStatus", "paymentSummary", "paymentInstructions", "paymentPreference", "customerSnapshot", "fulfillment", "notes", "createdAt", "updatedAt", "inventoryStatus"}
    data = serialize_document({k: v for k, v in order.items() if k in fields})
    data["statusHistory"] = [{k: v for k, v in row.items() if k in {"field", "from", "to", "status", "fromStatus", "toStatus", "createdAt", "changedAt"}} for row in serialize_document(order).get("statusHistory", [])]
    for line in data.get("items", []):
        line.pop("costPrice", None)
        if "stockSnapshot" in line:
            line["stockSnapshot"] = customer_stock_snapshot(line["stockSnapshot"])
    return data
