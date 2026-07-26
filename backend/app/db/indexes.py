import logging

from app.db.mongodb import get_database, get_mongo_status

logger = logging.getLogger(__name__)


async def create_indexes() -> None:
    status = await get_mongo_status()
    if not status["connected"]:
        logger.warning("Skipping index creation because MongoDB is not connected.")
        return

    db = get_database()
    try:
        await db.users.drop_index("email_1")
    except Exception:
        pass
    await db.users.create_index("email", unique=True, sparse=True)
    try:
        await db.users.drop_index("phone_1")
    except Exception:
        pass
    await db.users.create_index("phone", unique=True, sparse=True)
    await db.users.create_index("accountType")
    await db.users.create_index("globalRole")
    await db.users.create_index("status")
    await db.customer_profiles.create_index("userId", unique=True)
    await db.customer_profiles.create_index("phone")
    await db.tenants.create_index("slug", unique=True)
    await db.tenants.create_index("ownerUserId")
    await db.tenants.create_index("businessCategoryId")
    await db.tenants.create_index("status")
    await db.tenants.create_index("websiteStatus")
    await db.business_categories.create_index("slug", unique=True)
    await db.business_categories.create_index("isActive")
    await db.modules.create_index("code", unique=True)
    await db.modules.create_index("isActive")
    await db.tenant_modules.create_index([("tenantId", 1), ("moduleCode", 1)], unique=True)
    await db.tenant_modules.create_index("status")
    await db.custom_field_definitions.create_index(
        [("tenantId", 1), ("moduleCode", 1), ("entityType", 1), ("key", 1)],
        unique=True,
    )
    await db.custom_field_definitions.create_index([("tenantId", 1), ("entityType", 1)])
    await db.custom_field_definitions.create_index("isActive")
    await db.customers.create_index("tenantId")
    await db.customers.create_index([("tenantId", 1), ("phone", 1)])
    await db.customers.create_index([("tenantId", 1), ("email", 1)])
    await db.customers.create_index([("tenantId", 1), ("status", 1)])
    await db.customers.create_index("customerUserId")
    await db.item_categories.create_index([("tenantId", 1), ("slug", 1)], unique=True)
    await db.item_categories.create_index([("tenantId", 1), ("isActive", 1)])
    await db.items.create_index("tenantId")
    await db.items.create_index([("tenantId", 1), ("sku", 1)])
    await db.items.create_index([("tenantId", 1), ("status", 1)])
    await db.items.create_index([("tenantId", 1), ("itemType", 1)])
    await db.items.create_index([("tenantId", 1), ("categoryId", 1)])
    await db.item_imports.create_index("tenantId")
    await db.knowledge_documents.create_index([("tenantId", 1), ("sourceType", 1), ("sourceId", 1)], unique=True)
    await db.knowledge_documents.create_index([("tenantId", 1), ("moduleCode", 1)])
    await db.knowledge_documents.create_index([("tenantId", 1), ("sourceType", 1), ("createdAt", -1)])
    await db.knowledge_documents.create_index([("tenantId", 1), ("tags", 1)])
    await db.knowledge_documents.create_index([("tenantId", 1), ("isActive", 1), ("updatedAt", -1)])
    await db.transactions.create_index("tenantId")
    await db.transactions.create_index([("tenantId", 1), ("transactionNumber", 1)], unique=True)
    await db.transactions.create_index([("tenantId", 1), ("status", 1)])
    await db.transactions.create_index([("tenantId", 1), ("source", 1)])
    await db.transactions.create_index("customerUserId")
    await db.transactions.create_index("customerProfileId")
    await db.transactions.create_index([("tenantId", 1), ("paymentStatus", 1)])
    await db.transactions.create_index([("tenantId", 1), ("inventoryStatus", 1)])
    await db.payment_settings.create_index("tenantId", unique=True)
    await db.payment_records.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.payment_records.create_index([("tenantId", 1), ("transactionId", 1)])
    await db.payment_records.create_index([("tenantId", 1), ("status", 1), ("createdAt", -1)])
    await db.payment_records.create_index([("tenantId", 1), ("method", 1), ("createdAt", -1)])
    await db.payment_records.create_index([("provider", 1), ("providerSessionId", 1)])
    await db.payment_records.create_index([("provider", 1), ("providerPaymentIntentId", 1)])
    await db.stripe_webhook_events.create_index("eventId", unique=True)
    await db.stripe_webhook_events.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.stripe_webhook_events.create_index([("status", 1), ("createdAt", -1)])
    await db.inventory_movements.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.inventory_movements.create_index([("tenantId", 1), ("transactionId", 1)])
    await db.inventory_movements.create_index([("tenantId", 1), ("itemId", 1), ("createdAt", -1)])
    await db.carts.create_index([("customerUserId", 1), ("tenantId", 1), ("status", 1)])
    await db.carts.create_index("tenantId")
    await db.customer_favorites.create_index([("customerUserId", 1), ("tenantId", 1), ("itemId", 1)], unique=True)
    await db.customer_favorites.create_index([("customerUserId", 1), ("createdAt", -1)])
    await db.customer_notifications.create_index([("customerUserId", 1), ("status", 1), ("createdAt", -1)])
    await db.customer_notifications.create_index([("customerUserId", 1), ("tenantId", 1)])
    await db.business_notifications.create_index([("tenantId", 1), ("status", 1), ("createdAt", -1)])
    await db.business_notifications.create_index([("tenantId", 1), ("type", 1), ("createdAt", -1)])
    await db.whatsapp_integrations.create_index("tenantId", unique=True)
    await db.whatsapp_integrations.create_index("normalizedBusinessWhatsAppNumber")
    await db.whatsapp_integrations.create_index("phoneNumberId")
    await db.whatsapp_integrations.create_index("wabaId")
    await db.whatsapp_integrations.create_index("metaBusinessId")
    await db.whatsapp_integrations.create_index("connectionStatus")
    await db.whatsapp_integrations.create_index("webhookVerifyToken")
    await db.whatsapp_message_logs.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.whatsapp_message_logs.create_index([("conversationId", 1), ("createdAt", 1)])
    await db.whatsapp_message_logs.create_index([("tenantId", 1), ("direction", 1), ("providerMessageId", 1)])
    await db.whatsapp_message_logs.create_index("providerMessageId")
    await db.whatsapp_routing_events.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.whatsapp_routing_events.create_index([("phoneNumberId", 1), ("createdAt", -1)])
    await db.whatsapp_routing_events.create_index([("eventType", 1), ("createdAt", -1)])
    await db.whatsapp_go_live_runs.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.whatsapp_go_live_runs.create_index([("tenantId", 1), ("result", 1)])
    try:
        await db.business_notifications.drop_index("tenantId_1_sourceKey_1")
    except Exception:
        pass
    await db.business_notifications.create_index(
        [("tenantId", 1), ("sourceKey", 1)],
        unique=True,
        partialFilterExpression={"sourceKey": {"$exists": True}},
        name="tenantId_1_sourceKey_1",
    )
    await db.report_snapshots.create_index([("tenantId", 1), ("reportType", 1), ("summaryDate", 1)], unique=True)
    await db.report_delivery_settings.create_index("tenantId", unique=True)
    await db.report_delivery_logs.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.report_delivery_logs.create_index([("tenantId", 1), ("summaryDate", 1), ("channel", 1)])
    await db.sms_message_logs.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.conversations.create_index([("tenantId", 1), ("customerUserId", 1), ("channel", 1), ("status", 1)])
    await db.conversations.create_index([("tenantId", 1), ("ownerUserId", 1), ("channel", 1), ("status", 1)])
    await db.conversations.create_index([("tenantId", 1), ("channel", 1), ("externalCustomerPhone", 1), ("status", 1)])
    await db.conversations.create_index("lastMessageAt")
    await db.messages.create_index([("conversationId", 1), ("createdAt", 1)])
    await db.messages.create_index([("tenantId", 1), ("sender", 1)])
    await db.otp_challenges.create_index([("phone", 1), ("accountType", 1), ("purpose", 1), ("status", 1)])
    await db.otp_challenges.create_index([("email", 1), ("accountType", 1), ("purpose", 1), ("status", 1)])
    await db.otp_challenges.create_index("expiresAt", expireAfterSeconds=86400)
    await db.otp_challenges.create_index("createdAt")
    await db.qa_demo_runs.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.qa_demo_runs.create_index([("tenantId", 1), ("result", 1)])
    await db.submission_signoffs.create_index([("tenantId", 1), ("createdAt", -1)])
    await db.submission_signoffs.create_index([("tenantId", 1), ("status", 1)])
    logger.info("MongoDB indexes are ready.")
