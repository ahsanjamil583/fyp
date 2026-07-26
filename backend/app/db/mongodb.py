import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

client: AsyncIOMotorClient | None = None
database: AsyncIOMotorDatabase | None = None
mongo_available: bool = False


async def connect_to_mongo() -> None:
    global client, database, mongo_available

    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=2000)
    database = client[settings.mongodb_db_name]

    try:
        await client.admin.command("ping")
        mongo_available = True
        logger.info("Connected to MongoDB database '%s'.", settings.mongodb_db_name)
    except Exception as exc:
        mongo_available = False
        logger.warning("MongoDB is not reachable yet: %s", exc)


async def close_mongo_connection() -> None:
    global client, database, mongo_available

    if client:
        client.close()
    client = None
    database = None
    mongo_available = False


def get_database() -> AsyncIOMotorDatabase:
    if database is None:
        raise RuntimeError("MongoDB connection has not been initialized.")
    return database


async def get_mongo_status() -> dict[str, Any]:
    if client is None:
        return {"configured": True, "connected": False}

    try:
        await client.admin.command("ping")
        return {"configured": True, "connected": True}
    except Exception:
        return {"configured": True, "connected": False}
