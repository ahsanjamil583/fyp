import re

from app.db.mongodb import get_database


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "business"


async def generate_unique_tenant_slug(name: str) -> str:
    db = get_database()
    base = slugify(name)
    slug = base
    counter = 2

    while await db.tenants.find_one({"slug": slug}):
        slug = f"{base}-{counter}"
        counter += 1
    return slug
