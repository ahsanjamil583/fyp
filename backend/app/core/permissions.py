from bson import ObjectId
from fastapi import HTTPException, status

from app.db.mongodb import get_database


def require_platform_admin(user: dict) -> None:
    if user.get("globalRole") != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin access required.")


async def get_owned_tenant_or_403(tenant_id: ObjectId, user: dict) -> dict:
    db = get_database()
    query = {"_id": tenant_id}
    if user.get("globalRole") != "platform_admin":
        query["ownerUserId"] = user["_id"]

    tenant = await db.tenants.find_one(query)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found or access denied.")
    return tenant
