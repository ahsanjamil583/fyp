"""Archive duplicate catalog items and clean up what they left behind.

Repeated imports and double-submitted create forms produced several identical
active items per tenant: same name, same price, empty SKU. Customers saw the same
product twice and the AI counted it twice, because each copy also has its own
knowledge-base document and Chroma vectors.

The oldest copy of each group is kept. A duplicate that is referenced by a
transaction, cart, or favourite is never touched, so the run is safe to repeat.

    python scripts/dedupe_catalog_items.py
    python scripts/dedupe_catalog_items.py --apply
"""

import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database  # noqa: E402
from app.services.rag_vector_service import delete_knowledge_document_vectors  # noqa: E402


def _group_key(item: dict) -> tuple:
    """Items are duplicates when a customer could not tell them apart."""
    return (
        item.get("tenantId"),
        item.get("branchId"),
        str(item.get("name", "")).strip().lower(),
        float(item.get("price", 0) or 0),
        str(item.get("sku", "")).strip().lower(),
    )


async def _reference_count(db, item_id) -> int:
    return sum(
        [
            await db.transactions.count_documents({"items.itemId": item_id}),
            await db.carts.count_documents({"items.itemId": item_id}),
            await db.customer_favorites.count_documents({"itemId": item_id}),
        ]
    )


async def dedupe(apply_changes: bool) -> int:
    await connect_to_mongo()
    db = get_database()

    groups = defaultdict(list)
    async for item in db.items.find({"status": "active"}):
        groups[_group_key(item)].append(item)

    archived = 0
    skipped = 0
    vectors_removed = 0

    for key, items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda row: (row.get("createdAt") or datetime.min.replace(tzinfo=timezone.utc), str(row["_id"])))
        keeper, duplicates = items[0], items[1:]
        tenant = await db.tenants.find_one({"_id": keeper.get("tenantId")}, {"name": 1})
        print(f"\n{(tenant or {}).get('name', '?')} — {keeper.get('name')!r} x{len(items)}")
        print(f"  keep    {keeper['_id']}  created {keeper.get('createdAt')}")

        for duplicate in duplicates:
            references = await _reference_count(db, duplicate["_id"])
            if references:
                skipped += 1
                print(f"  SKIP    {duplicate['_id']}  referenced by {references} record(s)")
                continue

            print(f"  archive {duplicate['_id']}  created {duplicate.get('createdAt')}")
            orphans = await db.knowledge_documents.find({"sourceId": duplicate["_id"]}).to_list(50)
            for orphan in orphans:
                print(f"          + drop knowledge document {orphan['_id']} and its vectors")
                vectors_removed += 1
                if apply_changes:
                    try:
                        delete_knowledge_document_vectors(orphan)
                    except Exception as exc:  # a missing collection must not block the archive
                        print(f"          ! vector cleanup skipped: {exc}")
                    await db.knowledge_documents.delete_one({"_id": orphan["_id"]})

            archived += 1
            if apply_changes:
                await db.items.update_one(
                    {"_id": duplicate["_id"]},
                    {
                        "$set": {
                            "status": "archived",
                            "archivedReason": "duplicate_of:" + str(keeper["_id"]),
                            "updatedAt": datetime.now(timezone.utc),
                        }
                    },
                )

    verb = "Archived" if apply_changes else "Would archive"
    print(f"\n{verb} {archived} duplicate item(s); removed {vectors_removed} knowledge document(s); skipped {skipped} referenced duplicate(s).")
    if not apply_changes:
        print("Dry run only. Re-run with --apply to write the changes.")

    await close_mongo_connection()
    return archived


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the changes instead of reporting them.")
    args = parser.parse_args()
    asyncio.run(dedupe(args.apply))


if __name__ == "__main__":
    main()
