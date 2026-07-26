from fastapi import HTTPException, status

from app.db.mongodb import get_database


async def get_customer_profile_and_user(current_user: dict) -> tuple[dict, str]:
    db = get_database()
    user_id = str(current_user["_id"])
    profile = await db.customer_profiles.find_one({"userId": user_id})
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer profile not found.")
    return profile, user_id


async def get_marketplace_tenant_or_404(slug: str) -> dict:
    db = get_database()
    tenant = await db.tenants.find_one(
        {
            "slug": slug,
            "status": "active",
            "websiteStatus": "published",
            "settings.publicVisibility": True,
            "enabledModuleCodes": "customer_portal",
        }
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketplace business not found.")
    return tenant
