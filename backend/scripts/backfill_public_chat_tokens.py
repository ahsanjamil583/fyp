"""Give existing website conversations an opaque session token.

Public chat used to identify a conversation by its MongoDB ObjectId, which is a
timestamp plus a counter and can therefore be walked to read other visitors'
transcripts. Conversations created before that change have no token and would be
unreachable, so each one gets a random token here.

    python scripts/backfill_public_chat_tokens.py
    python scripts/backfill_public_chat_tokens.py --apply
"""

import argparse
import asyncio
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database  # noqa: E402


async def backfill(apply_changes: bool) -> int:
    await connect_to_mongo()
    db = get_database()

    query = {"channel": "website", "publicSessionToken": {"$exists": False}}
    pending = await db.conversations.count_documents(query)
    print(f"Website conversations without a session token: {pending}")

    updated = 0
    async for conversation in db.conversations.find(query, {"_id": 1}):
        if apply_changes:
            await db.conversations.update_one(
                {"_id": conversation["_id"]},
                {"$set": {"publicSessionToken": secrets.token_urlsafe(24)}},
            )
        updated += 1

    verb = "Assigned tokens to" if apply_changes else "Would assign tokens to"
    print(f"{verb} {updated} conversation(s).")
    if not apply_changes:
        print("Dry run only. Re-run with --apply to write the changes.")

    await close_mongo_connection()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the tokens instead of reporting them.")
    args = parser.parse_args()
    asyncio.run(backfill(args.apply))


if __name__ == "__main__":
    main()
