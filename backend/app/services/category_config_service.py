from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException, status

from app.db.mongodb import get_database
from app.services.custom_field_service import SUPPORTED_FIELD_TYPES, _normalize_field_options, _normalize_validation

TEMPLATE_DEFAULT_SECTIONS = {
    "default": ["hero", "metrics", "catalog", "services", "transaction_form", "contact"],
    "catalog": ["hero", "metrics", "catalog", "transaction_form", "testimonials", "contact"],
    "service": ["hero", "metrics", "services", "faq", "transaction_form", "contact"],
}
DEFAULT_TEMPLATE_RULES = {
    "recommendedTemplate": "default",
    "recommendedPrimaryColor": "#2563EB",
    "recommendedVisualPreset": "harbor",
    "heroStyle": "general-purpose",
    "sectionPriority": TEMPLATE_DEFAULT_SECTIONS["default"],
    "supportedTemplates": ["default", "catalog", "service"],
}
DEFAULT_AI_HINTS = {
    "businessPurpose": "Help customers understand the business and next steps.",
    "safetyNotes": "Stay grounded in tenant data and ask clarifying questions when information is missing.",
}
DEFAULT_FULFILLMENT_RULES = {
    "defaultType": "none",
    "allowedTypes": ["none"],
    "supportsDelivery": False,
    "supportsPickup": False,
    "supportsInPerson": True,
    "addressRequiredTypes": ["delivery"],
}


def _derive_visual_preset(template_code: str, hero_style: str, category_slug: str) -> str:
    combined = f"{hero_style} {category_slug}".lower()
    if template_code == "catalog":
        if "fashion" in combined or "visual" in combined:
            return "bazaar"
        return "market"
    if template_code == "service":
        if "clinic" in combined or "care" in combined or "trust" in combined:
            return "care"
        return "studio"
    if "food" in combined or "menu" in combined or "showcase" in combined:
        return "aurora"
    return "harbor"


def _derive_template_rules(category: dict) -> dict:
    raw_website_hints = category.get("websiteHints") or {}
    website_hints = dict(raw_website_hints) if isinstance(raw_website_hints, dict) else {}
    template_code = str(website_hints.get("recommendedTemplate") or DEFAULT_TEMPLATE_RULES["recommendedTemplate"]).strip().lower()
    if template_code not in TEMPLATE_DEFAULT_SECTIONS:
        template_code = DEFAULT_TEMPLATE_RULES["recommendedTemplate"]
    hero_style = str(website_hints.get("heroStyle") or DEFAULT_TEMPLATE_RULES["heroStyle"]).strip() or DEFAULT_TEMPLATE_RULES["heroStyle"]
    section_priority = website_hints.get("sectionPriority")
    if not isinstance(section_priority, list) or not section_priority:
        section_priority = TEMPLATE_DEFAULT_SECTIONS[template_code]
    return {
        "recommendedTemplate": template_code,
        "recommendedPrimaryColor": str(website_hints.get("recommendedPrimaryColor") or DEFAULT_TEMPLATE_RULES["recommendedPrimaryColor"]),
        "recommendedVisualPreset": str(
            website_hints.get("recommendedVisualPreset")
            or _derive_visual_preset(template_code, hero_style, str(category.get("slug") or ""))
        ),
        "heroStyle": hero_style,
        "sectionPriority": [str(item).strip() for item in section_priority if str(item).strip()],
        "supportedTemplates": [template_code] if template_code in {"catalog", "service"} else DEFAULT_TEMPLATE_RULES["supportedTemplates"],
    }


def _derive_fulfillment_rules(category: dict) -> dict:
    raw_fulfillment_hints = category.get("fulfillmentHints") or {}
    fulfillment_hints = dict(raw_fulfillment_hints) if isinstance(raw_fulfillment_hints, dict) else {}
    allowed_types = []
    if bool(fulfillment_hints.get("supportsDelivery")):
        allowed_types.append("delivery")
    if bool(fulfillment_hints.get("supportsPickup")):
        allowed_types.append("pickup")
    if bool(fulfillment_hints.get("supportsInPerson", True)) or not allowed_types:
        allowed_types.insert(0, "none")

    default_mode = str(fulfillment_hints.get("defaultMode") or "").strip().lower()
    default_type_map = {
        "delivery": "delivery",
        "pickup": "pickup",
        "delivery_or_pickup": "delivery" if "delivery" in allowed_types else "pickup",
        "pickup_or_delivery": "pickup" if "pickup" in allowed_types else "delivery",
        "in_person_service": "none",
        "consultation": "none",
        "custom": "none",
        "none": "none",
    }
    default_type = default_type_map.get(default_mode, allowed_types[0] if allowed_types else DEFAULT_FULFILLMENT_RULES["defaultType"])
    if default_type not in allowed_types:
        default_type = allowed_types[0] if allowed_types else DEFAULT_FULFILLMENT_RULES["defaultType"]

    return {
        "defaultMode": default_mode or "none",
        "defaultType": default_type,
        "allowedTypes": allowed_types or DEFAULT_FULFILLMENT_RULES["allowedTypes"],
        "supportsDelivery": "delivery" in allowed_types,
        "supportsPickup": "pickup" in allowed_types,
        "supportsInPerson": "none" in allowed_types,
        "addressRequiredTypes": ["delivery"],
    }


def _derive_analytics_config(category: dict) -> dict:
    raw_suggestions = category.get("analyticsSuggestions") or []
    if not isinstance(raw_suggestions, list):
        raw_suggestions = []
    suggestions = [str(item).strip() for item in raw_suggestions if str(item).strip()]
    slug = str(category.get("slug") or "").lower()
    focus_metrics = ["totalTransactions", "marketplaceOrderCount", "grossRevenue"]
    if any(token in slug for token in ["restaurant", "bakery", "retail", "pharmacy", "electronics", "fashion"]):
        focus_metrics.extend(["topItems", "lowStockItems"])
    if any(token in slug for token in ["clinic", "salon", "repair", "education", "gym", "services"]):
        focus_metrics.extend(["totalBookings", "totalInquiries", "inquiryResponseRate"])
    if "quote" in " ".join(suggestions).lower():
        focus_metrics.append("quoteApprovalRate")
    return {
        "suggestions": suggestions,
        "focusMetrics": list(dict.fromkeys(focus_metrics)),
    }


def _derive_ai_config(category: dict) -> dict:
    raw_prompt_fragments = category.get("aiPromptFragments") or []
    if not isinstance(raw_prompt_fragments, list):
        raw_prompt_fragments = []
    prompt_fragments = [str(item).strip() for item in raw_prompt_fragments if str(item).strip()]
    ai_hints = dict(DEFAULT_AI_HINTS)
    raw_ai_hints = category.get("aiHints") or {}
    if isinstance(raw_ai_hints, dict):
        ai_hints.update(raw_ai_hints)
    return {
        "hints": ai_hints,
        "promptFragments": prompt_fragments,
    }


def build_category_runtime_config(category: dict | None) -> dict:
    if not category:
        return {
            "name": "",
            "slug": "",
            "templateRules": dict(DEFAULT_TEMPLATE_RULES),
            "fulfillmentRules": dict(DEFAULT_FULFILLMENT_RULES),
            "analyticsConfig": {"suggestions": [], "focusMetrics": ["totalTransactions", "grossRevenue"]},
            "aiConfig": {"hints": dict(DEFAULT_AI_HINTS), "promptFragments": []},
            "defaultCustomFields": [],
            "suggestedModules": [],
        }

    return {
        "name": category.get("name", ""),
        "slug": category.get("slug", ""),
        "templateRules": _derive_template_rules(category),
        "fulfillmentRules": _derive_fulfillment_rules(category),
        "analyticsConfig": _derive_analytics_config(category),
        "aiConfig": _derive_ai_config(category),
        "defaultCustomFields": category.get("defaultCustomFields") if isinstance(category.get("defaultCustomFields"), list) else [],
        "suggestedModules": category.get("suggestedModules") if isinstance(category.get("suggestedModules"), list) else [],
    }


def hydrate_category_document(category: dict) -> dict:
    runtime = build_category_runtime_config(category)
    return {
        **category,
        "defaultCustomFields": runtime["defaultCustomFields"],
        "suggestedModules": runtime["suggestedModules"],
        "templateRules": runtime["templateRules"],
        "fulfillmentRules": runtime["fulfillmentRules"],
        "analyticsConfig": runtime["analyticsConfig"],
        "aiConfig": runtime["aiConfig"],
    }


def build_tenant_category_hints(category: dict | None) -> dict:
    runtime = build_category_runtime_config(category)
    return {
        "categoryName": runtime["name"],
        "categorySlug": runtime["slug"],
        "suggestedModules": runtime["suggestedModules"],
        "template": runtime["templateRules"],
        "fulfillment": runtime["fulfillmentRules"],
        "analytics": runtime["analyticsConfig"],
        "ai": runtime["aiConfig"],
    }


def validate_tenant_fulfillment(tenant: dict, fulfillment: dict) -> dict:
    category_hints = ((tenant.get("settings") or {}).get("categoryHints") or {})
    rules = category_hints.get("fulfillment") or {}
    allowed_types = rules.get("allowedTypes") or DEFAULT_FULFILLMENT_RULES["allowedTypes"]
    fulfillment_type = str((fulfillment or {}).get("type") or "none").strip().lower()
    if fulfillment_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Fulfillment type '{fulfillment_type}' is not allowed for this business category.",
        )
    return rules


def build_category_analytics_insights(tenant: dict, summary: dict, conversion: dict, low_stock_items: list[dict]) -> list[dict]:
    category_hints = ((tenant.get("settings") or {}).get("categoryHints") or {})
    analytics_config = category_hints.get("analytics") or {}
    insights = []
    for suggestion in analytics_config.get("suggestions", []):
        suggestion_lower = suggestion.lower()
        status = "info"
        if "low-stock" in suggestion_lower or "stock" in suggestion_lower:
            status = "attention" if low_stock_items else "healthy"
        elif "repeat" in suggestion_lower:
            status = "info"
        elif "conversion" in suggestion_lower or "approval" in suggestion_lower:
            status = "attention" if float(conversion.get("quoteApprovalRate", 0) or 0) < 30 else "healthy"
        insights.append({"label": suggestion, "status": status})
    return insights


async def apply_category_default_custom_fields(tenant_oid: ObjectId, category: dict | None) -> None:
    if not category:
        return
    defaults = category.get("defaultCustomFields") or []
    if not isinstance(defaults, list) or not defaults:
        return

    db = get_database()
    now = datetime.now(timezone.utc)
    for index, field in enumerate(defaults, start=1):
        if not isinstance(field, dict):
            continue
        field_type = str(field.get("type") or "").strip()
        module_code = str(field.get("moduleCode") or "").strip()
        entity_type = str(field.get("entityType") or "").strip()
        key = str(field.get("key") or "").strip()
        label = str(field.get("label") or key.replace("_", " ").title()).strip()
        if field_type not in SUPPORTED_FIELD_TYPES or not module_code or not entity_type or not key or not label:
            continue
        existing = await db.custom_field_definitions.find_one(
            {"tenantId": tenant_oid, "moduleCode": module_code, "entityType": entity_type, "key": key}
        )
        if existing:
            continue
        await db.custom_field_definitions.insert_one(
            {
                "tenantId": tenant_oid,
                "moduleCode": module_code,
                "entityType": entity_type,
                "key": key,
                "label": label,
                "type": field_type,
                "required": bool(field.get("required", False)),
                "options": _normalize_field_options(field.get("options")),
                "defaultValue": field.get("defaultValue"),
                "validation": _normalize_validation(field.get("validation")),
                "showInTable": bool(field.get("showInTable", True)),
                "showInForm": bool(field.get("showInForm", True)),
                "order": int(field.get("order") or index),
                "isActive": bool(field.get("isActive", True)),
                "createdAt": now,
                "updatedAt": now,
                "seedSource": "category_default",
            }
        )
