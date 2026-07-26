import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.security import hash_password
from app.db.mongodb import get_database, get_mongo_status

logger = logging.getLogger(__name__)


async def seed_default_admin() -> None:
    status = await get_mongo_status()
    if not status["connected"]:
        logger.warning("Skipping default admin seed because MongoDB is not connected.")
        return

    if not all(
        [
            settings.default_admin_full_name,
            settings.default_admin_email,
            settings.default_admin_phone,
            settings.default_admin_password,
        ]
    ):
        logger.info("Default admin seed skipped because env values are incomplete.")
        return

    db = get_database()
    email = settings.default_admin_email.lower()
    existing = await db.users.find_one({"email": email})
    now = datetime.now(timezone.utc)

    if existing:
        await db.users.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "globalRole": "platform_admin",
                    "accountType": "business_owner",
                    "status": "active",
                    "updatedAt": now,
                }
            },
        )
        logger.info("Default admin already exists; role/status ensured.")
        return

    await db.users.insert_one(
        {
            "fullName": settings.default_admin_full_name,
            "email": email,
            "phone": settings.default_admin_phone,
            "passwordHash": hash_password(settings.default_admin_password),
            "accountType": "business_owner",
            "globalRole": "platform_admin",
            "status": "active",
            "isEmailVerified": False,
            "isPhoneVerified": False,
            "lastLoginAt": None,
            "createdAt": now,
            "updatedAt": now,
        }
    )
    logger.info("Default platform admin seeded.")
