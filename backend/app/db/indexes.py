import logging

from app.core.config import settings
from app.db.mongodb import get_database, get_mongo_status

logger = logging.getLogger(__name__)


async def _ensure_index(collection, keys, **options) -> None:
    """Create an index, tolerating one that already exists with a different spec.

    Mongo raises when an index with the same name exists with different options. That
    must not abort startup, so it is logged and left for a migration to change
    deliberately.

    A UNIQUE index is different: swallowing its failure leaves the collection with no
    uniqueness constraint at all while the application carries on assuming there is one.
    That is how a duplicate account slips in, so a unique index is logged at error level
    and the failure is raised.
    """
    try:
        await collection.create_index(keys, **options)
    except Exception as exc:
        if options.get("unique"):
            logger.error(
                "Could not create the UNIQUE index %r on %s: %s. Resolve the duplicates and restart; "
                "continuing would leave the collection with no uniqueness enforcement.",
                keys,
                collection.name,
                exc,
            )
            raise
        logger.warning("Could not create index %r on %s: %s", keys, collection.name, exc)


async def create_indexes() -> None:
    status = await get_mongo_status()
    if not status["connected"]:
        logger.warning("Skipping index creation because MongoDB is not connected.")
        return

    db = get_database()
    # These are created idempotently and never dropped. Dropping and recreating them on
    # every boot left a window with no uniqueness enforcement at all, raced when several
    # workers started together, and aborted startup outright if a duplicate slipped in
    # between the two calls. A spec change belongs in a one-off migration script.
    await _ensure_index(db.users, "email", unique=True, sparse=True)
    await _ensure_index(db.users, "phone", unique=True, sparse=True)
    await _ensure_index(db.users, "accountType")
    await _ensure_index(db.users, "globalRole")
    await _ensure_index(db.users, "status")
    await _ensure_index(db.customer_profiles, "userId", unique=True)
    await _ensure_index(db.customer_profiles, "phone")
    await _ensure_index(db.tenants, "slug", unique=True)
    await _ensure_index(db.tenants, "ownerUserId")
    await _ensure_index(db.tenants, "businessCategoryId")
    await _ensure_index(db.tenants, "status")
    await _ensure_index(db.tenants, "websiteStatus")
    await _ensure_index(db.business_categories, "slug", unique=True)
    await _ensure_index(db.business_categories, "isActive")
    await _ensure_index(db.modules, "code", unique=True)
    await _ensure_index(db.modules, "isActive")
    await _ensure_index(db.tenant_modules, [("tenantId", 1), ("moduleCode", 1)], unique=True)
    await _ensure_index(db.tenant_modules, "status")
    await _ensure_index(db.custom_field_definitions, 
        [("tenantId", 1), ("moduleCode", 1), ("entityType", 1), ("key", 1)],
        unique=True,
    )
    await _ensure_index(db.custom_field_definitions, [("tenantId", 1), ("entityType", 1)])
    await _ensure_index(db.custom_field_definitions, "isActive")
    await _ensure_index(db.customers, "tenantId")
    await _ensure_index(db.customers, [("tenantId", 1), ("phone", 1)])
    await _ensure_index(db.customers, [("tenantId", 1), ("email", 1)])
    await _ensure_index(db.customers, [("tenantId", 1), ("status", 1)])
    await _ensure_index(db.customers, "customerUserId")
    await _ensure_index(db.item_categories, [("tenantId", 1), ("slug", 1)], unique=True)
    await _ensure_index(db.item_categories, [("tenantId", 1), ("isActive", 1)])
    await _ensure_index(db.items, "tenantId")
    await _ensure_index(db.items, [("tenantId", 1), ("sku", 1)])
    await _ensure_index(db.items, [("tenantId", 1), ("status", 1)])
    await _ensure_index(db.items, [("tenantId", 1), ("itemType", 1)])
    await _ensure_index(db.items, [("tenantId", 1), ("categoryId", 1)])
    # Repeated imports and double-submitted forms created identical active items that
    # customers saw twice. Only active rows are constrained, so archiving a duplicate
    # remains the way to resolve one. Case-insensitive so "Blue Shirt" and "blue shirt"
    # collide. Run scripts/dedupe_catalog_items.py first if this index fails to build.
    await _ensure_index(db.items, 
        [("tenantId", 1), ("branchId", 1), ("name", 1), ("price", 1)],
        unique=True,
        partialFilterExpression={"status": "active"},
        collation={"locale": "en", "strength": 2},
        name="items_active_identity_unique",
    )
    # SKUs are optional and stored as "" when unset, so only non-empty ones are unique.
    await _ensure_index(db.items, 
        [("tenantId", 1), ("sku", 1)],
        unique=True,
        partialFilterExpression={"status": "active", "sku": {"$gt": ""}},
        name="items_active_sku_unique",
    )
    await _ensure_index(db.item_imports, "tenantId")
    await _ensure_index(db.knowledge_documents, [("tenantId", 1), ("sourceType", 1), ("sourceId", 1)], unique=True)
    await _ensure_index(db.knowledge_documents, [("tenantId", 1), ("moduleCode", 1)])
    await _ensure_index(db.knowledge_documents, [("tenantId", 1), ("sourceType", 1), ("createdAt", -1)])
    await _ensure_index(db.knowledge_documents, [("tenantId", 1), ("tags", 1)])
    await _ensure_index(db.knowledge_documents, [("tenantId", 1), ("isActive", 1), ("updatedAt", -1)])
    await _ensure_index(db.transactions, "tenantId")
    await _ensure_index(db.transactions, [("tenantId", 1), ("transactionNumber", 1)], unique=True)
    await _ensure_index(db.transactions, [("tenantId", 1), ("status", 1)])
    await _ensure_index(db.transactions, [("tenantId", 1), ("source", 1)])
    await _ensure_index(db.transactions, "customerUserId")
    await _ensure_index(db.transactions, "customerProfileId")
    await _ensure_index(db.transactions, [("tenantId", 1), ("paymentStatus", 1)])
    await _ensure_index(db.transactions, [("tenantId", 1), ("inventoryStatus", 1)])
    # Cashier accounts. One profile per (business, login) so an owner cannot register the
    # same person twice, and receipt tokens are the public handle for a cashier order.
    await _ensure_index(db.cashiers, [("tenantId", 1), ("userId", 1)], unique=True)
    await _ensure_index(db.cashiers, [("tenantId", 1), ("isActive", 1)])
    await _ensure_index(db.cashiers, "userId")
    await _ensure_index(db.transactions, 
        "receiptToken",
        unique=True,
        partialFilterExpression={"receiptToken": {"$type": "string"}},
        name="receiptToken_1",
    )
    await _ensure_index(db.transactions, [("tenantId", 1), ("cashier.cashierId", 1), ("createdAt", -1)])
    # Re-running the same sheet must not double the books, so both duplicate signatures
    # are indexed rather than scanned.
    await _ensure_index(db.transactions, [("tenantId", 1), ("importSignature.orderNumber", 1)])
    await _ensure_index(db.transactions, [("tenantId", 1), ("importSignature.fingerprint", 1)])
    await _ensure_index(db.order_imports, [("tenantId", 1), ("createdAt", -1)])
    # One confirmation per order, per event, per channel. The claim is written before the
    # message is sent, so a replayed gateway callback loses this race and sends nothing.
    await _ensure_index(db.order_message_deliveries, 
        [("transactionId", 1), ("event", 1), ("channel", 1)],
        unique=True,
        name="order_message_once",
    )
    await _ensure_index(db.order_message_deliveries, [("tenantId", 1), ("createdAt", -1)])
    await _ensure_index(db.order_message_settings, "tenantId", unique=True)
    await _ensure_index(db.payment_settings, "tenantId", unique=True)
    await _ensure_index(db.payment_records, [("tenantId", 1), ("createdAt", -1)])
    await _ensure_index(db.payment_records, [("tenantId", 1), ("transactionId", 1)])
    await _ensure_index(db.payment_records, [("tenantId", 1), ("status", 1), ("createdAt", -1)])
    await _ensure_index(db.payment_records, [("tenantId", 1), ("method", 1), ("createdAt", -1)])
    await _ensure_index(db.payment_records, [("provider", 1), ("providerSessionId", 1)])
    await _ensure_index(db.payment_records, [("provider", 1), ("providerPaymentIntentId", 1)])
    # Payment OTP challenges are kept apart from otp_challenges on purpose: a code minted
    # to settle a payment must never be presentable to a sign-in endpoint, or the reverse.
    await _ensure_index(db.payment_otp_challenges, [("paymentRecordId", 1), ("status", 1), ("createdAt", -1)])
    await _ensure_index(db.payment_otp_challenges, [("tenantId", 1), ("createdAt", -1)])
    # Rows outlive their 5-minute validity so a failed attempt stays auditable, then go.
    await _ensure_index(db.payment_otp_challenges, "expiresAt", expireAfterSeconds=86400)
    await _ensure_index(db.stripe_webhook_events, "eventId", unique=True)
    await _ensure_index(db.stripe_webhook_events, [("tenantId", 1), ("createdAt", -1)])
    await _ensure_index(db.stripe_webhook_events, [("status", 1), ("createdAt", -1)])
    await _ensure_index(db.inventory_movements, [("tenantId", 1), ("createdAt", -1)])
    await _ensure_index(db.inventory_movements, [("tenantId", 1), ("transactionId", 1)])
    await _ensure_index(db.inventory_movements, [("tenantId", 1), ("itemId", 1), ("createdAt", -1)])
    await _ensure_index(db.carts, [("customerUserId", 1), ("tenantId", 1), ("status", 1)])
    await _ensure_index(db.carts, "tenantId")
    await _ensure_index(db.customer_favorites, [("customerUserId", 1), ("tenantId", 1), ("itemId", 1)], unique=True)
    await _ensure_index(db.customer_favorites, [("customerUserId", 1), ("createdAt", -1)])
    await _ensure_index(db.customer_notifications, [("customerUserId", 1), ("status", 1), ("createdAt", -1)])
    await _ensure_index(db.customer_notifications, [("customerUserId", 1), ("tenantId", 1)])
    await _ensure_index(db.business_notifications, [("tenantId", 1), ("status", 1), ("createdAt", -1)])
    await _ensure_index(db.business_notifications, [("tenantId", 1), ("type", 1), ("createdAt", -1)])
    await _ensure_index(db.whatsapp_integrations, "tenantId", unique=True)
    await _ensure_index(db.whatsapp_integrations, "normalizedBusinessWhatsAppNumber")
    await _ensure_index(db.whatsapp_integrations, "webhookVerifyToken")
    await _ensure_index(db.whatsapp_integrations, [("tenantId", 1), ("bridgeToken", 1), ("provider", 1)])
    # WhatsApp logs hold customer phone numbers and full message bodies. Without a TTL
    # that is unbounded PII retention, so rows expire after the configured window.
    # A TTL window change has to be applied to the existing index, so this one is
    # deliberately re-created. It is not unique, so there is no uniqueness window to
    # lose, and _ensure_index keeps a failure from aborting startup.
    try:
        await db.whatsapp_message_logs.drop_index("createdAt_1")
    except Exception:
        pass
    await _ensure_index(
        db.whatsapp_message_logs,
        "createdAt",
        expireAfterSeconds=settings.whatsapp_log_retention_days * 86400,
        name="createdAt_1",
    )
    await _ensure_index(db.whatsapp_message_logs, [("tenantId", 1), ("createdAt", -1)])
    await _ensure_index(db.whatsapp_message_logs, [("conversationId", 1), ("createdAt", 1)])
    await _ensure_index(db.whatsapp_message_logs, [("tenantId", 1), ("direction", 1), ("providerMessageId", 1)])
    await _ensure_index(db.whatsapp_security_events, [("tenantId", 1), ("createdAt", -1)])
    await _ensure_index(db.whatsapp_security_events, [("tenantId", 1), ("eventType", 1), ("createdAt", -1)])
    # Created idempotently and never dropped. Dropping a UNIQUE index on every boot left
    # a window with no uniqueness enforcement, raced across workers, and aborted startup
    # outright if a duplicate slipped in between the two calls.
    await _ensure_index(
        db.business_notifications,
        [("tenantId", 1), ("sourceKey", 1)],
        unique=True,
        partialFilterExpression={"sourceKey": {"$exists": True}},
        name="tenantId_1_sourceKey_1",
    )
    # Order submission claims: the _id is the fingerprint, so uniqueness is free. The TTL
    # is what keeps the collection from growing without bound.
    await _ensure_index(db.order_submission_claims, "expiresAt", expireAfterSeconds=0)
    await _ensure_index(db.report_snapshots, [("tenantId", 1), ("reportType", 1), ("summaryDate", 1)], unique=True)
    await _ensure_index(db.report_delivery_settings, "tenantId", unique=True)
    await _ensure_index(db.report_delivery_logs, [("tenantId", 1), ("createdAt", -1)])
    await _ensure_index(db.report_delivery_logs, [("tenantId", 1), ("summaryDate", 1), ("channel", 1)])
    await _ensure_index(db.sms_message_logs, [("tenantId", 1), ("createdAt", -1)])
    # SMS logs hold recipient numbers. Ninety days is enough for support and billing
    # questions, and keeping them indefinitely is a growing liability for no benefit.
    await _ensure_index(db.sms_message_logs, "createdAt", expireAfterSeconds=90 * 24 * 60 * 60)
    await _ensure_index(db.conversations, [("tenantId", 1), ("customerUserId", 1), ("channel", 1), ("status", 1)])
    await _ensure_index(db.conversations, [("tenantId", 1), ("ownerUserId", 1), ("channel", 1), ("status", 1)])
    await _ensure_index(db.conversations, [("tenantId", 1), ("channel", 1), ("externalCustomerPhone", 1), ("status", 1)])
    await _ensure_index(db.conversations, "lastMessageAt")
    await _ensure_index(db.conversations, 
        "publicSessionToken",
        unique=True,
        partialFilterExpression={"publicSessionToken": {"$type": "string"}},
        name="publicSessionToken_1",
    )
    await _ensure_index(db.messages, [("conversationId", 1), ("createdAt", 1)])
    await _ensure_index(db.messages, [("tenantId", 1), ("sender", 1)])
    await _ensure_index(db.otp_challenges, [("phone", 1), ("accountType", 1), ("purpose", 1), ("status", 1)])
    await _ensure_index(db.otp_challenges, [("email", 1), ("accountType", 1), ("purpose", 1), ("status", 1)])
    await _ensure_index(db.otp_challenges, "expiresAt", expireAfterSeconds=86400)
    await _ensure_index(db.otp_challenges, "createdAt")
    await _ensure_index(db.qa_demo_runs, [("tenantId", 1), ("createdAt", -1)])
    await _ensure_index(db.qa_demo_runs, [("tenantId", 1), ("result", 1)])
    await _ensure_index(db.submission_signoffs, [("tenantId", 1), ("createdAt", -1)])
    await _ensure_index(db.submission_signoffs, [("tenantId", 1), ("status", 1)])
    # Shared rate-limit windows; Mongo reclaims each one shortly after it closes.
    await _ensure_index(db.rate_limit_counters, "expiresAt", expireAfterSeconds=0, name="expiresAt_1")
    logger.info("MongoDB indexes are ready.")
