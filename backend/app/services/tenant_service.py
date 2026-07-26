from datetime import datetime, timezone
import re

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.core.module_guard import ensure_tenant_module_enabled
from app.core.permissions import get_owned_tenant_or_403
from app.core.slug import generate_unique_tenant_slug
from app.db.mongodb import get_database
from app.db.seeders.seed_business_categories import seed_business_categories
from app.services.category_config_service import apply_category_default_custom_fields, build_tenant_category_hints
from app.services.localization_service import PAKISTAN_PROVINCES, get_language_mode, normalize_optional_email, normalize_optional_pk_phone, normalize_province
from app.services.rag_index_service import index_tenant_profile_for_rag

PLAN_ORDER = ("starter", "growth", "scale")
PAID_PLAN_CODES = {"growth", "scale"}
ALLOWED_WEBSITE_TEMPLATES = {"default", "catalog", "service"}
ALLOWED_WEBSITE_SECTION_TYPES = {"hero", "metrics", "catalog", "services", "transaction_form", "testimonials", "faq", "contact"}
ALLOWED_WEBSITE_PRESETS = {
    "default": {"aurora", "harbor"},
    "catalog": {"market", "bazaar"},
    "service": {"studio", "care"},
}
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _compute_phase3_onboarding(tenant: dict) -> dict:
    contact = tenant.get("contact", {})
    address = tenant.get("address", {})
    checks = [
        bool(str(tenant.get("name", "")).strip()),
        bool(tenant.get("businessCategoryId")),
        bool(str(contact.get("phone", "")).strip() or str(contact.get("email", "")).strip()),
        bool(str(address.get("city", "")).strip() and str(address.get("province", "")).strip()),
        bool(str(tenant.get("description", "")).strip()),
    ]
    completed_steps = sum(1 for item in checks if item)
    current_step = 3 if completed_steps >= len(checks) else min(3, (completed_steps // 2) + 1)

    existing = (((tenant.get("settings") or {}).get("onboarding") or {}).get("phase3") or {})
    return {
        "completedSteps": completed_steps,
        "totalSteps": len(checks),
        "currentStep": int(existing.get("currentStep") or current_step),
        "isComplete": completed_steps == len(checks),
        "completedAt": existing.get("completedAt"),
    }


def _merge_tenant_settings(base_settings: dict | None, extra_settings: dict | None, tenant_snapshot: dict | None = None) -> dict:
    merged = {
        "currency": "PKR",
        "timezone": "Asia/Karachi",
        "languageMode": "mixed",
        "publicVisibility": True,
        "planCode": "starter",
    }
    if base_settings:
        merged.update(base_settings)
    if extra_settings:
        merged.update(extra_settings)
    merged["languageMode"] = get_language_mode(merged)
    onboarding = dict((merged.get("onboarding") or {}))
    if tenant_snapshot is not None:
        phase3 = _compute_phase3_onboarding({**tenant_snapshot, "settings": merged})
        if phase3["isComplete"] and not phase3.get("completedAt"):
            phase3["completedAt"] = datetime.now(timezone.utc).isoformat()
        onboarding["phase3"] = phase3
        merged["onboarding"] = onboarding
    return merged


def _normalize_contact(contact: dict | None) -> dict:
    contact = contact or {}
    return {
        "email": normalize_optional_email(contact.get("email")),
        "phone": normalize_optional_pk_phone(contact.get("phone")),
        "whatsapp": normalize_optional_pk_phone(contact.get("whatsapp")),
    }


def _normalize_address(address: dict | None) -> dict:
    address = address or {}
    return {
        "line1": str(address.get("line1") or "").strip(),
        "city": str(address.get("city") or "").strip(),
        "province": normalize_province(address.get("province")) if str(address.get("province") or "").strip() else "",
        "country": "Pakistan",
    }


def _default_website_sections(template_code: str) -> list[dict]:
    if template_code == "catalog":
        order = ["hero", "metrics", "catalog", "transaction_form", "testimonials", "contact"]
    elif template_code == "service":
        order = ["hero", "metrics", "services", "faq", "transaction_form", "contact"]
    else:
        order = ["hero", "metrics", "catalog", "services", "transaction_form", "contact"]
    return [
        {"type": section_type, "label": section_type.replace("_", " ").title(), "visible": True, "order": index + 1, "content": {}}
        for index, section_type in enumerate(order)
    ]


def _build_default_website_settings(website_hints: dict, tenant_name: str) -> dict:
    template_code = website_hints.get("recommendedTemplate", "default")
    primary_color = website_hints.get("recommendedPrimaryColor", "#2563EB")
    visual_preset = "studio" if template_code == "service" else "market" if template_code == "catalog" else "harbor"
    return {
        "templateCode": template_code,
        "visualPreset": visual_preset,
        "primaryColor": primary_color,
        "sections": _default_website_sections(template_code),
        "hero": {
            "headline": f"{tenant_name} made easy to browse, book, and contact online.",
            "subheadline": "Show your offers, answer common questions, and let customers take action from one polished page.",
            "ctaLabel": "Start now",
            "secondaryCtaLabel": "Browse offers",
        },
        "testimonials": [],
        "faq": [],
        "seo": {},
    }


def _validate_hex_color(value: str) -> str:
    color = str(value or "").strip()
    if not HEX_COLOR_PATTERN.match(color):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid website primary color.")
    return color


def _normalize_text_field(value, fallback: str = "", max_length: int = 500) -> str:
    text = str(value or fallback).strip()
    if len(text) > max_length:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Website text content is too long.")
    return text


def _normalize_website_sections(sections, template_code: str) -> list[dict]:
    if not sections:
        return _default_website_sections(template_code)
    if not isinstance(sections, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Website sections must be a list.")

    normalized = []
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Each website section must be an object.")
        section_type = str(section.get("type") or "").strip()
        if section_type not in ALLOWED_WEBSITE_SECTION_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid website section type.")
        label = _normalize_text_field(section.get("label"), fallback=section_type.replace("_", " ").title(), max_length=80)
        content = section.get("content") or {}
        if not isinstance(content, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Website section content must be an object.")
        raw_order = section.get("order", index)
        try:
            order = int(raw_order)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Website section order must be numeric.")
        if order < 1:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Website section order must be at least 1.")
        normalized.append(
            {
                "type": section_type,
                "label": label,
                "visible": bool(section.get("visible", True)),
                "order": order,
                "content": content,
            }
        )
    return sorted(normalized, key=lambda item: (item["order"], item["type"]))


def _normalize_testimonials(rows) -> list[dict]:
    if rows in (None, ""):
        return []
    if not isinstance(rows, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Testimonials must be a list.")
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Each testimonial must be an object.")
        normalized.append(
            {
                "quote": _normalize_text_field(row.get("quote"), max_length=500),
                "name": _normalize_text_field(row.get("name"), max_length=120),
                "role": _normalize_text_field(row.get("role"), max_length=160),
            }
        )
    return normalized


def _normalize_faq(rows) -> list[dict]:
    if rows in (None, ""):
        return []
    if not isinstance(rows, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="FAQ must be a list.")
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Each FAQ row must be an object.")
        normalized.append(
            {
                "question": _normalize_text_field(row.get("question"), max_length=180),
                "answer": _normalize_text_field(row.get("answer"), max_length=1000),
            }
        )
    return normalized


def _normalize_website_settings(website_settings: dict | None, tenant_name: str) -> dict:
    if website_settings is None:
        return {}
    if not isinstance(website_settings, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Website settings must be an object.")

    template_code = str(website_settings.get("templateCode") or "default").strip().lower()
    if template_code not in ALLOWED_WEBSITE_TEMPLATES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid website template.")

    defaults = _build_default_website_settings({}, tenant_name)
    default_preset = defaults["visualPreset"] if defaults["templateCode"] == template_code else _build_default_website_settings({"recommendedTemplate": template_code}, tenant_name)["visualPreset"]
    visual_preset = str(website_settings.get("visualPreset") or default_preset).strip().lower()
    if visual_preset not in ALLOWED_WEBSITE_PRESETS.get(template_code, set()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid website visual preset.")

    hero = website_settings.get("hero") or {}
    if not isinstance(hero, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Website hero content must be an object.")
    seo = website_settings.get("seo") or {}
    if not isinstance(seo, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Website SEO settings must be an object.")

    return {
        "templateCode": template_code,
        "visualPreset": visual_preset,
        "primaryColor": _validate_hex_color(website_settings.get("primaryColor") or defaults["primaryColor"]),
        "sections": _normalize_website_sections(website_settings.get("sections"), template_code),
        "hero": {
            "headline": _normalize_text_field(hero.get("headline"), fallback=defaults["hero"]["headline"], max_length=200),
            "subheadline": _normalize_text_field(hero.get("subheadline"), fallback=defaults["hero"]["subheadline"], max_length=600),
            "ctaLabel": _normalize_text_field(hero.get("ctaLabel"), fallback=defaults["hero"]["ctaLabel"], max_length=40),
            "secondaryCtaLabel": _normalize_text_field(hero.get("secondaryCtaLabel"), fallback=defaults["hero"]["secondaryCtaLabel"], max_length=40),
        },
        "testimonials": _normalize_testimonials(website_settings.get("testimonials")),
        "faq": _normalize_faq(website_settings.get("faq")),
        "seo": {
            "title": _normalize_text_field(seo.get("title"), max_length=160),
            "description": _normalize_text_field(seo.get("description"), max_length=320),
        },
    }


def _normalize_plan_code(plan_code: str | None) -> str:
    normalized = str(plan_code or "starter").lower()
    return normalized if normalized in PLAN_ORDER else "starter"


async def _get_active_business_category(category_id: str | None) -> dict | None:
    if not category_id:
        return None

    db = get_database()
    category = None
    if ObjectId.is_valid(str(category_id)):
        category = await db.business_categories.find_one({"_id": ObjectId(category_id), "isActive": True})
    else:
        category = await db.business_categories.find_one({"slug": str(category_id).strip(), "isActive": True})
    if not category:
        await seed_business_categories()
        if ObjectId.is_valid(str(category_id)):
            category = await db.business_categories.find_one({"_id": ObjectId(category_id), "isActive": True})
        else:
            category = await db.business_categories.find_one({"slug": str(category_id).strip(), "isActive": True})
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business category not found.")
    return category


async def _resolve_active_business_category_id(category_id: str | None) -> ObjectId | None:
    category = await _get_active_business_category(category_id)
    return category["_id"] if category else None


async def _validate_plan_change(tenant: dict, next_settings: dict) -> None:
    db = get_database()
    plan_code = _normalize_plan_code(next_settings.get("planCode"))
    enabled_codes = tenant.get("enabledModuleCodes", [])
    if not enabled_codes:
        return

    blocked_modules = []
    async for module in db.modules.find({"code": {"$in": enabled_codes}, "isActive": True}):
        included_plans = ((module.get("availability") or {}).get("includedPlans")) or list(PLAN_ORDER)
        if plan_code not in included_plans:
            blocked_modules.append(module.get("name", module.get("code", "module")))

    if blocked_modules:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Disable or upgrade restricted modules before switching to the {plan_code} plan: {', '.join(blocked_modules)}.",
        )


def _paid_plan_access_status(tenant: dict, plan_code: str) -> str:
    if plan_code not in PAID_PLAN_CODES:
        return "approved"
    access = (((tenant.get("settings") or {}).get("packageAccess") or {}).get(plan_code) or {})
    return str(access.get("status") or "locked").lower()


def _ensure_plan_change_allowed(existing: dict, next_settings: dict, user: dict) -> None:
    current_plan = _normalize_plan_code((existing.get("settings") or {}).get("planCode"))
    next_plan = _normalize_plan_code(next_settings.get("planCode"))
    if next_plan == current_plan:
        return
    if user.get("globalRole") == "platform_admin":
        return
    if next_plan in PAID_PLAN_CODES and _paid_plan_access_status(existing, next_plan) != "approved":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Paid packages require payment or admin approval before they can be activated.",
        )


async def _validate_tenant_publish_ready(tenant: dict) -> None:
    db = get_database()
    if not tenant.get("name"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Business name is required before publishing.")

    contact = tenant.get("contact", {})
    if not contact.get("phone") and not contact.get("email"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add a business phone or email before publishing.",
        )

    website_settings = tenant.get("websiteSettings", {})
    if not website_settings.get("templateCode"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select website settings before publishing.",
        )
    _normalize_website_settings(website_settings, tenant.get("name", "Business"))

    if "items" in tenant.get("enabledModuleCodes", []):
        public_items = await db.items.count_documents(
            {
                "tenantId": tenant["_id"],
                "status": "active",
                "$or": [{"isSellable": True}, {"isBookable": True}],
            }
        )
        if public_items == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Add at least one active sellable or bookable item before publishing.",
            )


async def create_tenant(payload, owner: dict) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    category = await _get_active_business_category(payload.businessCategoryId)
    category_id = category["_id"] if category else None
    website_hints = category.get("websiteHints", {}) if category else {}
    fulfillment_hints = category.get("fulfillmentHints", {}) if category else {}

    tenant = {
        "name": payload.name,
        "slug": await generate_unique_tenant_slug(payload.name),
        "businessCategoryId": category_id,
        "ownerUserId": owner["_id"],
        "description": payload.description,
        "logo": {},
        "coverImage": {},
        "contact": _normalize_contact({**payload.contact, "email": payload.contact.get("email", owner.get("email", "")), "phone": payload.contact.get("phone", owner.get("phone", ""))}),
        "address": _normalize_address(payload.address),
        "status": "draft",
        "websiteStatus": "not_generated",
        "enabledModuleCodes": [],
        "customFields": {},
        "createdAt": now,
        "updatedAt": now,
    }
    tenant["settings"] = _merge_tenant_settings(None, payload.settings, tenant)
    tenant["settings"]["categoryHints"] = build_tenant_category_hints(category)
    tenant["websiteSettings"] = _build_default_website_settings(website_hints, tenant["name"])

    result = await db.tenants.insert_one(tenant)
    tenant["_id"] = result.inserted_id
    await apply_category_default_custom_fields(tenant["_id"], category)
    await index_tenant_profile_for_rag(tenant)
    return serialize_document(tenant)


async def list_my_tenants(owner: dict) -> list[dict]:
    db = get_database()
    cursor = db.tenants.find({"ownerUserId": owner["_id"]}).sort("createdAt", -1)
    return [serialize_document(tenant) async for tenant in cursor]


async def get_tenant(tenant_id: str, user: dict) -> dict:
    tenant = await get_owned_tenant_or_403(parse_object_id(tenant_id, "tenantId"), user)
    return serialize_document(tenant)


async def update_tenant(tenant_id: str, payload, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)

    existing = await get_owned_tenant_or_403(tenant_oid, user)
    update = {"updatedAt": datetime.now(timezone.utc)}
    for key in ["name", "description", "contact", "address", "settings", "websiteSettings"]:
        value = getattr(payload, key)
        if value is not None:
            if key == "contact":
                value = _normalize_contact(value)
            elif key == "address":
                value = _normalize_address(value)
            update[key] = value

    category = None
    if payload.businessCategoryId is not None:
        category = await _get_active_business_category(payload.businessCategoryId)
        update["businessCategoryId"] = category["_id"] if category else None

    if payload.name:
        if existing and existing["name"] != payload.name:
            update["slug"] = await generate_unique_tenant_slug(payload.name)

    merged_snapshot = {**existing, **update}
    update["settings"] = _merge_tenant_settings(existing.get("settings"), update.get("settings"), merged_snapshot)
    _ensure_plan_change_allowed(existing, update["settings"], user)
    if payload.websiteSettings is not None:
        merged_website_settings = {**(existing.get("websiteSettings") or {}), **(payload.websiteSettings or {})}
        update["websiteSettings"] = _normalize_website_settings(merged_website_settings, update.get("name") or existing.get("name", "Business"))
    await _validate_plan_change(existing, update["settings"])
    if category:
        update["settings"]["categoryHints"] = build_tenant_category_hints(category)
        if payload.websiteSettings is None:
            existing_template = (((existing.get("websiteSettings") or {}).get("templateCode")) or "default")
            if existing_template in {"default", "catalog", "service"}:
                update["websiteSettings"] = {
                    **_build_default_website_settings(category.get("websiteHints", {}), update.get("name") or existing.get("name", "")),
                    **(existing.get("websiteSettings") or {}),
                    "templateCode": category.get("websiteHints", {}).get("recommendedTemplate", existing_template),
                    "primaryColor": category.get("websiteHints", {}).get(
                        "recommendedPrimaryColor",
                        (existing.get("websiteSettings") or {}).get("primaryColor", "#2563EB"),
                    ),
                }
    if "websiteSettings" in update:
        update["websiteSettings"] = _normalize_website_settings(update["websiteSettings"], update.get("name") or existing.get("name", "Business"))

    await db.tenants.update_one({"_id": tenant_oid}, {"$set": update})
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    if category:
        await apply_category_default_custom_fields(tenant_oid, category)
    await index_tenant_profile_for_rag(tenant)
    return serialize_document(tenant)


async def publish_tenant(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await ensure_tenant_module_enabled(tenant_oid, "website_builder")
    await _validate_tenant_publish_ready(tenant)
    await db.tenants.update_one(
        {"_id": tenant_oid},
        {"$set": {"status": "active", "websiteStatus": "published", "updatedAt": datetime.now(timezone.utc)}},
    )
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await index_tenant_profile_for_rag(tenant)
    return serialize_document(tenant)


async def unpublish_tenant(tenant_id: str, user: dict) -> dict:
    db = get_database()
    tenant_oid = parse_object_id(tenant_id, "tenantId")
    await get_owned_tenant_or_403(tenant_oid, user)
    await db.tenants.update_one(
        {"_id": tenant_oid},
        {"$set": {"websiteStatus": "unpublished", "updatedAt": datetime.now(timezone.utc)}},
    )
    tenant = await get_owned_tenant_or_403(tenant_oid, user)
    await index_tenant_profile_for_rag(tenant)
    return serialize_document(tenant)


async def audit_log(action: str, actor_id: ObjectId, tenant_id: ObjectId | None = None, metadata: dict | None = None) -> None:
    db = get_database()
    await db.audit_logs.insert_one(
        {
            "action": action,
            "actorUserId": actor_id,
            "tenantId": tenant_id,
            "metadata": metadata or {},
            "createdAt": datetime.now(timezone.utc),
        }
    )
