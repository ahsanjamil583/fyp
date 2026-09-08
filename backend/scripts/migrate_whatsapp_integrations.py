"""Repair WhatsApp integration rows left inconsistent by the Baileys migration.

Two problems are fixed:

1. Boolean toggles stored as ``None``. ``dict.get(key, True)`` does not fall back
   for an explicit null, so these rows silently disabled the WhatsApp agent.
2. Integrations still pinned to the retired ``meta_cloud`` provider. That value is
   no longer accepted, so the rows show as connected while being unusable.

Run a dry run first, then apply:

    python scripts/migrate_whatsapp_integrations.py
    python scripts/migrate_whatsapp_integrations.py --apply
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database  # noqa: E402
from app.services.whatsapp_service import normalize_phone  # noqa: E402

BOOLEAN_FLAGS = ("agentEnabled", "autoReplyEnabled", "handoffEnabled")
SUPPORTED_PROVIDERS = {"mock", "baileys"}


async def migrate(apply_changes: bool) -> int:
    await connect_to_mongo()
    db = get_database()

    null_flag_fixes = 0
    provider_fixes = 0
    number_fixes = 0

    async for integration in db.whatsapp_integrations.find({}):
        tenant = await db.tenants.find_one({"_id": integration.get("tenantId")}, {"name": 1})
        label = (tenant or {}).get("name", integration.get("tenantId"))
        update: dict = {}

        for flag in BOOLEAN_FLAGS:
            if flag in integration and integration[flag] is None:
                update[flag] = True
                print(f"  [null-flag] {label}: {flag} None -> True")

        provider = str(integration.get("provider") or "").strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            update["provider"] = "mock"
            update["isConnected"] = False
            update["status"] = "needs_reconnect"
            print(f"  [provider]  {label}: {provider!r} -> 'mock', marked needs_reconnect")

        # Older rows kept raw user input ("+1 555-627-7647", "03345625097") here while the
        # normalized field held E.164, so the two disagreed and display was inconsistent.
        stored_number = integration.get("businessWhatsAppNumber") or ""
        canonical = normalize_phone(stored_number)
        if canonical and canonical != stored_number:
            update["businessWhatsAppNumber"] = canonical
            update["normalizedBusinessWhatsAppNumber"] = canonical
            print(f"  [number]    {label}: {stored_number!r} -> {canonical!r}")

        if not update:
            continue

        if any(flag in update for flag in BOOLEAN_FLAGS):
            null_flag_fixes += 1
        if "businessWhatsAppNumber" in update:
            number_fixes += 1
        if "provider" in update:
            provider_fixes += 1

        if apply_changes:
            await db.whatsapp_integrations.update_one({"_id": integration["_id"]}, {"$set": update})

    verb = "Updated" if apply_changes else "Would update"
    print(
        f"\n{verb} {null_flag_fixes} row(s) with null toggles, {provider_fixes} row(s) on a retired provider, "
        f"and {number_fixes} row(s) with a non-canonical phone number."
    )
    if not apply_changes:
        print("Dry run only. Re-run with --apply to write the changes.")

    await close_mongo_connection()
    return null_flag_fixes + provider_fixes + number_fixes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the changes instead of reporting them.")
    args = parser.parse_args()
    asyncio.run(migrate(args.apply))


if __name__ == "__main__":
    main()
