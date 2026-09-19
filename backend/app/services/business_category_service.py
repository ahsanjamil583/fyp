from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.object_ids import parse_object_id, serialize_document
from app.core.slug import slugify
from app.db.seeders.seed_business_categories import default_business_categories, seed_business_categories
from app.db.mongodb import get_database
from app.services.category_config_service import hydrate_category_document


async def list_public_categories() -> list[dict]:
    db = get_database()
    cursor = db.business_categories.find({"isActive": True}).sort("name", 1)
    categories = [hydrate_category_document(serialize_document(category)) async for category in cursor]
    if categories:
        return categories

    await seed_business_categories()
    cursor = db.business_categories.find({"isActive": True}).sort("name", 1)
    categories = [hydrate_category_document(serialize_document(category)) async for category in cursor]
    if categories:
        return categories

    now = datetime.now(timezone.utc).isoformat()
    return [
        hydrate_category_document(
            {
                **category,
                "id": category["slug"],
                "isActive": True,
                "defaultCustomFields": category.get("defaultCustomFields", []),
                "createdAt": now,
                "updatedAt": now,
            }
        )
        for category in sorted(default_business_categories(), key=lambda item: item["name"])
    ]


async def list_admin_categories() -> list[dict]:
    db = get_database()
    cursor = db.business_categories.find({}).sort("name", 1)
    return [hydrate_category_document(serialize_document(category)) async for category in cursor]


async def create_category(payload) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    slug = slugify(payload.slug or payload.name)
    if await db.business_categories.find_one({"slug": slug}):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category slug already exists.")

    category = {
        "name": payload.name,
        "slug": slug,
        "description": payload.description,
        "icon": payload.icon,
        "isActive": payload.isActive,
        "suggestedModules": payload.suggestedModules,
        "defaultCustomFields": payload.defaultCustomFields,
        "aiHints": payload.aiHints,
        "aiPromptFragments": payload.aiPromptFragments,
        "websiteHints": payload.websiteHints,
        "fulfillmentHints": payload.fulfillmentHints,
        "analyticsSuggestions": payload.analyticsSuggestions,
        "createdAt": now,
        "updatedAt": now,
    }
    category["_id"] = (await db.business_categories.insert_one(category)).inserted_id
    return hydrate_category_document(serialize_document(category))


async def update_category(category_id: str, payload) -> dict:
    db = get_database()
    category_oid = parse_object_id(category_id, "categoryId")
    existing = await db.business_categories.find_one({"_id": category_oid})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    update = {"updatedAt": datetime.now(timezone.utc)}
    for key in [
        "name",
        "description",
        "icon",
        "isActive",
        "suggestedModules",
        "defaultCustomFields",
        "aiHints",
        "aiPromptFragments",
        "websiteHints",
        "fulfillmentHints",
        "analyticsSuggestions",
    ]:
        value = getattr(payload, key)
        if value is not None:
            update[key] = value
    if payload.slug is not None:
        slug = slugify(payload.slug)
        # create_category checks this; update did not, so an edit could collide and
        # tenant lookups by slug would then return whichever category matched first.
        if await db.business_categories.find_one({"slug": slug, "_id": {"$ne": category_oid}}):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category slug already exists.")
        update["slug"] = slug

    await db.business_categories.update_one({"_id": category_oid}, {"$set": update})
    return hydrate_category_document(serialize_document(await db.business_categories.find_one({"_id": category_oid})))


async def delete_category(category_id: str) -> dict:
    db = get_database()
    category_oid = parse_object_id(category_id, "categoryId")
    result = await db.business_categories.update_one(
        {"_id": category_oid},
        {"$set": {"isActive": False, "updatedAt": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    return hydrate_category_document(serialize_document(await db.business_categories.find_one({"_id": category_oid})))
