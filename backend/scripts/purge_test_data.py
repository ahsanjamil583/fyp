"""Report (and optionally remove) throwaway tenants and accounts left by past test runs.

The database has accumulated fixtures from automated phase testing — tenants named
"Phase 8 Disabled Tenant 1781725626", users at @example.com — which make the admin
screens and the owner agent's counts noisy at demo time.

DESTRUCTIVE. It defaults to a dry run and prints exactly what it would delete. Review
that list before using --apply, and take a backup first:

    python scripts/backup_mongo.py
    python scripts/purge_test_data.py
    python scripts/purge_test_data.py --apply
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database  # noqa: E402

# Names produced by the phase test scripts: a label plus a run timestamp.
TEST_TENANT_NAME = re.compile(r"^(phase\s*\d+|phase\d+|live phase)\b.*\d{6,}$", re.IGNORECASE)
TEST_EMAIL = re.compile(r"@example\.com$", re.IGNORECASE)

# Collections keyed by tenantId that should follow their tenant out.
TENANT_SCOPED = (
    "items", "item_categories", "item_imports", "customers", "transactions", "carts",
    "conversations", "messages", "knowledge_documents", "custom_field_definitions",
    "tenant_modules", "payment_settings", "payment_records", "inventory_movements",
    "business_notifications", "customer_notifications", "whatsapp_integrations",
    "whatsapp_message_logs", "report_delivery_settings", "report_delivery_logs",
    "report_snapshots", "qa_demo_runs", "submission_signoffs",
)


def looks_like_test_tenant(tenant: dict) -> bool:
    return bool(TEST_TENANT_NAME.match(str(tenant.get("name", "")).strip()))


async def purge(apply_changes: bool) -> None:
    await connect_to_mongo()
    db = get_database()

    tenants = [t for t in await db.tenants.find({}).to_list(length=1000) if looks_like_test_tenant(t)]
    tenant_ids = [t["_id"] for t in tenants]

    print(f"Test-looking tenants: {len(tenants)}")
    for tenant in tenants:
        print(f"  - {tenant.get('name')} ({tenant['_id']}) status={tenant.get('status')}")

    print("\nTenant-scoped documents that would be removed:")
    total_docs = 0
    if tenant_ids:
        for name in TENANT_SCOPED:
            count = await db[name].count_documents({"tenantId": {"$in": tenant_ids}})
            if count:
                total_docs += count
                print(f"  {name:26} {count}")
    print(f"  {'TOTAL':26} {total_docs}")

    owner_ids = [t.get("ownerUserId") for t in tenants if t.get("ownerUserId")]
    users = await db.users.find({"$or": [{"email": {"$regex": TEST_EMAIL.pattern, "$options": "i"}}, {"_id": {"$in": owner_ids}}]}).to_list(length=1000)
    # Never remove an account that still owns a tenant being kept.
    keep = set()
    for user in users:
        owned = await db.tenants.count_documents({"ownerUserId": user["_id"], "_id": {"$nin": tenant_ids}})
        if owned:
            keep.add(user["_id"])
    removable = [u for u in users if u["_id"] not in keep]

    print(f"\nTest-looking users: {len(removable)} (protecting {len(keep)} that still own a live tenant)")
    for user in removable[:20]:
        print(f"  - {user.get('email') or user.get('phone')} ({user.get('accountType')})")
    if len(removable) > 20:
        print(f"  ... and {len(removable) - 20} more")

    if not apply_changes:
        print("\nDRY RUN. Nothing was deleted. Re-run with --apply after taking a backup.")
        await close_mongo_connection()
        return

    for name in TENANT_SCOPED:
        await db[name].delete_many({"tenantId": {"$in": tenant_ids}})
    await db.tenants.delete_many({"_id": {"$in": tenant_ids}})
    await db.users.delete_many({"_id": {"$in": [u["_id"] for u in removable]}})
    await db.customer_profiles.delete_many({"userId": {"$in": [u["_id"] for u in removable]}})
    print(f"\nRemoved {len(tenants)} tenant(s), {total_docs} scoped document(s), and {len(removable)} user(s).")

    await close_mongo_connection()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually delete. Take a backup first.")
    args = parser.parse_args()
    asyncio.run(purge(args.apply))


if __name__ == "__main__":
    main()
