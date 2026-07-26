import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

from bson import json_util

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database

DEFAULT_COLLECTIONS = [
    "users",
    "customer_profiles",
    "tenants",
    "business_categories",
    "modules",
    "tenant_modules",
    "custom_field_definitions",
    "customers",
    "item_categories",
    "items",
    "transactions",
    "carts",
    "customer_notifications",
    "business_notifications",
    "report_snapshots",
    "audit_logs",
]


async def export_backup(output_dir: Path, collections: list[str]) -> Path:
    await connect_to_mongo()
    try:
        db = get_database()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = output_dir / f"bizxus_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "database": settings.mongodb_db_name,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "collections": [],
        }

        for collection_name in collections:
            rows = await db[collection_name].find({}).to_list(length=None)
            target = backup_dir / f"{collection_name}.json"
            target.write_text(json_util.dumps(rows, indent=2), encoding="utf-8")
            manifest["collections"].append({"name": collection_name, "count": len(rows), "file": target.name})

        (backup_dir / "manifest.json").write_text(json_util.dumps(manifest, indent=2), encoding="utf-8")
        return backup_dir
    finally:
        await close_mongo_connection()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a JSON backup of BizxusAI MongoDB collections.")
    parser.add_argument("--output-dir", default=settings.backup_dir, help="Directory where the backup folder should be created.")
    parser.add_argument("--collections", nargs="*", default=DEFAULT_COLLECTIONS, help="Optional explicit list of collections to export.")
    args = parser.parse_args()

    backup_dir = asyncio.run(export_backup(Path(args.output_dir).resolve(), args.collections))
    print(f"Backup completed: {backup_dir}")


if __name__ == "__main__":
    main()
