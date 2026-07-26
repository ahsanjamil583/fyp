"""Seed a complete demo workspace for the final BizXusAI FYP demo.

Run from backend/:
    python scripts/seed_demo_data.py

The script is idempotent. It creates/updates demo users, one generalized business,
modules, catalog items with color/size variants, knowledge-base documents, a customer,
conversation samples, payment/report settings, and a sample order.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bson import ObjectId

from app.core.security import hash_password
from app.core.slug import slugify
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database, get_mongo_status
from app.db.seeders.seed_business_categories import seed_business_categories
from app.db.seeders.seed_modules import seed_modules

DEMO_OWNER_EMAIL = "owner@bizxus.demo"
DEMO_CUSTOMER_EMAIL = "customer@bizxus.demo"
DEMO_ADMIN_EMAIL = "admin@bizxus.demo"
DEMO_PASSWORD = "Demo@12345"
DEMO_ADMIN_PASSWORD = "Admin@12345"
DEMO_SLUG = "demo-bazaar"
DEMO_OWNER_PHONE = "+923001111111"
DEMO_CUSTOMER_PHONE = "+923002222222"
DEMO_WHATSAPP_VERIFY_TOKEN = "bizxus-demo-whatsapp-token"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def upsert_user(email: str, full_name: str, phone: str, account_type: str, password: str, global_role: str = "user") -> ObjectId:
    db = get_database()
    existing = await db.users.find_one({"email": email})
    doc = {
        "fullName": full_name,
        "email": email,
        "phone": phone,
        "passwordHash": hash_password(password),
        "accountType": account_type,
        "globalRole": global_role,
        "status": "active",
        "isEmailVerified": True,
        "isPhoneVerified": True,
        "lastLoginAt": None,
        "updatedAt": now_utc(),
    }
    if existing:
        await db.users.update_one({"_id": existing["_id"]}, {"$set": doc})
        return existing["_id"]
    doc["createdAt"] = now_utc()
    return (await db.users.insert_one(doc)).inserted_id


async def ensure_category() -> ObjectId:
    db = get_database()
    category = await db.business_categories.find_one({"slug": "general-commerce"})
    if category:
        return category["_id"]
    doc = {
        "name": "General Commerce",
        "slug": "general-commerce",
        "description": "Flexible catalog business for FYP demo shops, boutiques, grocery stores, and service sellers.",
        "icon": "Store",
        "isActive": True,
        "suggestedModules": ["items", "website_builder", "customer_portal", "ai_chat", "whatsapp_agent", "payments", "analytics", "reports", "notifications", "owner_agent"],
        "defaultCustomFields": [],
        "aiHints": ["Understand Roman Urdu product queries.", "Match color, size, budget, and delivery intent.", "Create draft orders only after checking catalog and stock."],
        "aiPromptFragments": [],
        "websiteHints": {"recommendedTemplate": "catalog", "recommendedPrimaryColor": "#2563EB"},
        "fulfillmentHints": {"supportsDelivery": True, "supportsPickup": True},
        "analyticsSuggestions": ["Top selling items", "Low stock", "Pending orders"],
        "createdAt": now_utc(),
        "updatedAt": now_utc(),
    }
    return (await db.business_categories.insert_one(doc)).inserted_id


async def ensure_demo_tenant(owner_id: ObjectId, category_id: ObjectId) -> ObjectId:
    db = get_database()
    existing = await db.tenants.find_one({"slug": DEMO_SLUG})
    doc = {
        "ownerUserId": owner_id,
        "businessCategoryId": category_id,
        "name": "Demo Bazaar",
        "slug": DEMO_SLUG,
        "description": "A generalized BizXusAI demo store with catalog, WhatsApp agent, RAG knowledge base, smart ordering, stock, payments, and reports.",
        "contact": {"email": DEMO_OWNER_EMAIL, "phone": DEMO_OWNER_PHONE, "whatsapp": DEMO_OWNER_PHONE},
        "address": {"line1": "Main Road", "city": "Attock", "province": "Punjab", "country": "Pakistan"},
        "settings": {
            "currency": "PKR",
            "timezone": "Asia/Karachi",
            "languageMode": "mixed",
            "publicVisibility": True,
            "planCode": "scale",
            "reportDelivery": {
                "enabled": True,
                "channels": ["whatsapp", "sms"],
                "recipients": ["+923001111111"],
                "time": "20:00",
                "timezone": "Asia/Karachi",
                "languageMode": "mixed",
            },
            "paymentSettings": {
                "cod": {"enabled": True, "label": "Cash on Delivery"},
                "manual": {"enabled": True, "instructions": "Send payment screenshot on WhatsApp."},
                "jazzcash": {"enabled": True, "accountTitle": "Demo Bazaar", "accountNumber": "03001111111", "mode": "manual"},
                "easypaisa": {"enabled": True, "accountTitle": "Demo Bazaar", "accountNumber": "03001111111", "mode": "manual"},
            },
            "whatsappAgent": {"enabled": True, "provider": "mock", "phoneNumber": DEMO_OWNER_PHONE, "humanHandoffKeywords": ["human", "agent", "owner"]},
        },
        "websiteSettings": {
            "templateCode": "catalog",
            "visualPreset": "market",
            "primaryColor": "#2563EB",
            "hero": {
                "headline": "Demo Bazaar — order anything through AI chat",
                "subheadline": "Ask in Roman Urdu, choose colors/sizes, and confirm COD/manual orders.",
                "ctaLabel": "Chat with AI",
                "secondaryCtaLabel": "Browse catalog",
            },
            "sections": [
                {"type": "hero", "label": "Hero", "visible": True, "order": 1, "content": {}},
                {"type": "catalog", "label": "Catalog", "visible": True, "order": 2, "content": {}},
                {"type": "faq", "label": "FAQ", "visible": True, "order": 3, "content": {}},
                {"type": "contact", "label": "Contact", "visible": True, "order": 4, "content": {}},
            ],
            "faq": [
                {"question": "Delivery time kya hai?", "answer": "Attock city mein same-day delivery, baqi areas mein 1-2 days."},
                {"question": "Payment kaise karni hai?", "answer": "COD, manual bank transfer, JazzCash, aur EasyPaisa demo modes available hain."},
            ],
            "testimonials": [],
            "seo": {"title": "Demo Bazaar by BizXusAI"},
        },
        "enabledModuleCodes": ["items", "customers", "website_builder", "customer_portal", "ai_chat", "whatsapp_agent", "analytics", "payments", "reports", "notifications", "owner_agent"],
        "status": "active",
        "websiteStatus": "published",
        "rag": {"indexStatus": "ready", "knowledgeDocumentCount": 2, "activeKnowledgeDocumentCount": 2, "chunkCount": 0, "embeddingProvider": "demo"},
        "updatedAt": now_utc(),
    }
    if existing:
        await db.tenants.update_one({"_id": existing["_id"]}, {"$set": doc})
        return existing["_id"]
    doc["createdAt"] = now_utc()
    return (await db.tenants.insert_one(doc)).inserted_id


async def enable_modules(tenant_id: ObjectId, owner_id: ObjectId) -> None:
    db = get_database()
    modules = ["items", "customers", "website_builder", "customer_portal", "ai_chat", "whatsapp_agent", "analytics", "payments", "reports", "notifications", "owner_agent"]
    for module_code in modules:
        await db.tenant_modules.update_one(
            {"tenantId": tenant_id, "moduleCode": module_code},
            {"$set": {"status": "enabled", "config": {}, "enabledBy": owner_id, "enabledAt": now_utc(), "updatedAt": now_utc()}},
            upsert=True,
        )


async def seed_items(tenant_id: ObjectId) -> list[ObjectId]:
    db = get_database()
    await db.item_categories.delete_many({"tenantId": tenant_id})
    await db.items.delete_many({"tenantId": tenant_id})
    clothing_id = ObjectId()
    food_id = ObjectId()
    await db.item_categories.insert_many([
        {"_id": clothing_id, "tenantId": tenant_id, "name": "Clothing", "slug": "clothing", "description": "Color and size based products", "parentCategoryId": None, "isActive": True, "createdAt": now_utc(), "updatedAt": now_utc()},
        {"_id": food_id, "tenantId": tenant_id, "name": "Food", "slug": "food", "description": "Fast food demo items", "parentCategoryId": None, "isActive": True, "createdAt": now_utc(), "updatedAt": now_utc()},
    ])
    items = [
        {
            "_id": ObjectId(),
            "tenantId": tenant_id,
            "branchId": None,
            "itemType": "product",
            "name": "Premium Hoodie",
            "description": "Warm cotton hoodie available in black, red, and navy. Best for winter casual wear.",
            "categoryId": clothing_id,
            "sku": "HOODIE-001",
            "price": 2499,
            "costPrice": 1600,
            "currency": "PKR",
            "unit": "piece",
            "images": [],
            "status": "active",
            "isSellable": True,
            "isBookable": False,
            "isStockTracked": True,
            "stock": {"quantity": 40, "lowStockThreshold": 5, "reservedQuantity": 0},
            "serviceDetails": {"durationMinutes": 0, "bufferMinutes": 0, "deliveryMode": "offsite"},
            "variants": [
                {"name": "Black / Medium", "sku": "HOODIE-BLK-M", "price": 2499, "compareAtPrice": 2999, "stockQuantity": 12, "reservedQuantity": 0, "lowStockThreshold": 3, "isDefault": True, "isActive": True, "optionValues": {"color": "Black", "size": "Medium", "material": "Cotton"}},
                {"name": "Black / Large", "sku": "HOODIE-BLK-L", "price": 2599, "compareAtPrice": 3099, "stockQuantity": 10, "reservedQuantity": 0, "lowStockThreshold": 3, "isDefault": False, "isActive": True, "optionValues": {"color": "Black", "size": "Large", "material": "Cotton"}},
                {"name": "Red / Medium", "sku": "HOODIE-RED-M", "price": 2499, "compareAtPrice": 2999, "stockQuantity": 8, "reservedQuantity": 0, "lowStockThreshold": 3, "isDefault": False, "isActive": True, "optionValues": {"color": "Red", "size": "Medium", "material": "Cotton"}},
            ],
            "bundleComponents": [],
            "customFields": {"material": "Cotton", "season": "Winter"},
            "tags": ["hoodie", "black", "red", "medium", "large", "winter"],
            "createdAt": now_utc(),
            "updatedAt": now_utc(),
        },
        {
            "_id": ObjectId(),
            "tenantId": tenant_id,
            "branchId": None,
            "itemType": "product",
            "name": "Classic Black Shoes",
            "description": "Comfortable black shoes available in size 41, 42, and 43.",
            "categoryId": clothing_id,
            "sku": "SHOE-BLK",
            "price": 3999,
            "costPrice": 2800,
            "currency": "PKR",
            "unit": "pair",
            "images": [],
            "status": "active",
            "isSellable": True,
            "isBookable": False,
            "isStockTracked": True,
            "stock": {"quantity": 20, "lowStockThreshold": 4, "reservedQuantity": 0},
            "serviceDetails": {"durationMinutes": 0, "bufferMinutes": 0, "deliveryMode": "offsite"},
            "variants": [
                {"name": "Black / 42", "sku": "SHOE-BLK-42", "price": 3999, "compareAtPrice": 4499, "stockQuantity": 7, "reservedQuantity": 0, "lowStockThreshold": 2, "isDefault": True, "isActive": True, "optionValues": {"color": "Black", "size": "42", "material": "Synthetic Leather"}},
                {"name": "Black / 43", "sku": "SHOE-BLK-43", "price": 3999, "compareAtPrice": 4499, "stockQuantity": 5, "reservedQuantity": 0, "lowStockThreshold": 2, "isDefault": False, "isActive": True, "optionValues": {"color": "Black", "size": "43", "material": "Synthetic Leather"}},
            ],
            "bundleComponents": [],
            "customFields": {"material": "Synthetic Leather"},
            "tags": ["shoes", "black", "size 42", "size 43"],
            "createdAt": now_utc(),
            "updatedAt": now_utc(),
        },
        {
            "_id": ObjectId(),
            "tenantId": tenant_id,
            "branchId": None,
            "itemType": "product",
            "name": "Zinger Burger",
            "description": "Crispy zinger burger with fries option. Delivery available in Attock city.",
            "categoryId": food_id,
            "sku": "FOOD-ZINGER",
            "price": 520,
            "costPrice": 310,
            "currency": "PKR",
            "unit": "piece",
            "images": [],
            "status": "active",
            "isSellable": True,
            "isBookable": False,
            "isStockTracked": True,
            "stock": {"quantity": 50, "lowStockThreshold": 10, "reservedQuantity": 0},
            "serviceDetails": {"durationMinutes": 0, "bufferMinutes": 0, "deliveryMode": "offsite"},
            "variants": [],
            "bundleComponents": [],
            "customFields": {"spiceLevel": "Medium"},
            "tags": ["burger", "zinger", "food", "under 600"],
            "createdAt": now_utc(),
            "updatedAt": now_utc(),
        },
    ]
    await db.items.insert_many(items)
    return [item["_id"] for item in items]


def build_demo_payment_settings(tenant_id: ObjectId, owner_id: ObjectId) -> dict:
    return {
        "tenantId": tenant_id,
        "codEnabled": True,
        "manualEnabled": True,
        "bankTransferEnabled": True,
        "jazzCashEnabled": True,
        "easyPaisaEnabled": True,
        "paymentsDemoMode": True,
        "requireOwnerApproval": True,
        "bankName": "Demo Bank",
        "jazzCashNumber": "03001111111",
        "jazzCashAccountTitle": "Demo Bazaar",
        "easyPaisaNumber": "03001111111",
        "easyPaisaAccountTitle": "Demo Bazaar",
        "bankAccountTitle": "Demo Bazaar",
        "bankAccountNumber": "PK00BIZXUSDEMO0001",
        "bankIban": "PK00BIZXUSDEMO0001",
        "defaultMethod": "cod",
        "customerInstructions": "COD, manual bank transfer, JazzCash, and EasyPaisa demo payments are available. No real money moves in mock mode.",
        "createdBy": owner_id,
        "updatedBy": owner_id,
    }


def build_demo_report_delivery_settings(tenant_id: ObjectId) -> dict:
    return {
        "tenantId": tenant_id,
        "enabled": True,
        "whatsappEnabled": True,
        "smsEnabled": True,
        "deliveryTime": "20:00",
        "timezone": "Asia/Karachi",
        "whatsappRecipient": DEMO_OWNER_PHONE,
        "smsRecipient": DEMO_OWNER_PHONE,
        "languageMode": "mixed",
        "includeLowStock": True,
        "includeTopItems": True,
        "includeRecentOrders": True,
        "lastDeliveryStatus": "seeded_demo",
    }


def build_demo_whatsapp_integration(tenant_id: ObjectId) -> dict:
    return {
        "tenantId": tenant_id,
        "provider": "mock",
        "businessWhatsAppNumber": DEMO_OWNER_PHONE,
        "normalizedBusinessWhatsAppNumber": DEMO_OWNER_PHONE,
        "displayName": "Demo Bazaar",
        "phoneNumberId": "demo-bazaar-mock-phone-id",
        "apiVersion": "v21.0",
        "webhookVerifyToken": DEMO_WHATSAPP_VERIFY_TOKEN,
        "accessToken": "",
        "isConnected": True,
        "autoReplyEnabled": True,
        "handoffEnabled": True,
        "handoffKeywords": ["human", "agent", "admin", "owner"],
        "welcomeMessage": "Assalam o Alaikum! Main Demo Bazaar ka BizXus AI assistant hoon. Aap product, price, stock, delivery ya order ke bare mein pooch sakte hain.",
        "status": "connected_mock",
    }


async def seed_demo_integrations(tenant_id: ObjectId, owner_id: ObjectId) -> None:
    db = get_database()
    now = now_utc()
    payment_settings = build_demo_payment_settings(tenant_id, owner_id)
    report_settings = build_demo_report_delivery_settings(tenant_id)
    whatsapp_settings = build_demo_whatsapp_integration(tenant_id)

    await db.payment_settings.update_one(
        {"tenantId": tenant_id},
        {"$set": {**payment_settings, "updatedAt": now}, "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )
    await db.report_delivery_settings.update_one(
        {"tenantId": tenant_id},
        {"$set": {**report_settings, "updatedAt": now}, "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )
    await db.whatsapp_integrations.update_one(
        {"tenantId": tenant_id},
        {"$set": {**whatsapp_settings, "updatedAt": now}, "$setOnInsert": {"createdAt": now}},
        upsert=True,
    )

    await db.report_delivery_logs.delete_many({"tenantId": tenant_id, "source": "demo_seed"})
    await db.report_delivery_logs.insert_one(
        {
            "tenantId": tenant_id,
            "source": "demo_seed",
            "summaryDate": now.date().isoformat(),
            "channel": "whatsapp",
            "recipient": DEMO_OWNER_PHONE,
            "status": "delivered",
            "attemptCount": 1,
            "message": "Seeded demo daily summary delivery log.",
            "provider": "mock",
            "createdAt": now,
            "updatedAt": now,
        }
    )


async def seed_business_data(tenant_id: ObjectId, customer_user_id: ObjectId, item_ids: list[ObjectId]) -> None:
    db = get_database()
    await db.knowledge_documents.delete_many({"tenantId": tenant_id, "sourceType": {"$in": ["owner_text", "demo"]}})
    await db.knowledge_documents.insert_many([
        {
            "tenantId": tenant_id,
            "sourceType": "owner_text",
            "title": "Delivery and Payment Policy",
            "content": "Delivery Attock city mein same-day hai. Delivery charges 150 PKR hain. COD, JazzCash, EasyPaisa, aur manual bank transfer accepted hain. Refund only damaged product par 24 hours ke andar possible hai.",
            "tags": ["delivery", "payment", "refund"],
            "isActive": True,
            "createdByUserId": None,
            "createdAt": now_utc(),
            "updatedAt": now_utc(),
        },
        {
            "tenantId": tenant_id,
            "sourceType": "owner_text",
            "title": "Size and Color Guide",
            "content": "Hoodies black, red aur navy colors mein available hain. Common sizes Medium aur Large hain. Shoes black color mein size 42 aur 43 available hain. Customer color/size bataye to exact variant select karna hai.",
            "tags": ["size", "color", "variants"],
            "isActive": True,
            "createdByUserId": None,
            "createdAt": now_utc(),
            "updatedAt": now_utc(),
        },
    ])

    await db.customer_profiles.update_one(
        {"userId": str(customer_user_id)},
        {"$set": {"phone": DEMO_CUSTOMER_PHONE, "defaultAddress": {"line1": "House 12", "city": "Attock", "province": "Punjab"}, "savedAddresses": [], "preferences": {}, "updatedAt": now_utc()}, "$setOnInsert": {"createdAt": now_utc()}},
        upsert=True,
    )
    await db.customers.update_one(
        {"tenantId": tenant_id, "email": DEMO_CUSTOMER_EMAIL},
        {"$set": {"tenantId": tenant_id, "name": "Demo Customer", "phone": DEMO_CUSTOMER_PHONE, "email": DEMO_CUSTOMER_EMAIL, "address": {"line1": "House 12", "city": "Attock", "province": "Punjab"}, "sourceTags": ["customer_portal", "demo"], "stats": {"totalOrders": 1, "totalSpent": 520}, "updatedAt": now_utc()}, "$setOnInsert": {"createdAt": now_utc()}},
        upsert=True,
    )
    customer = await db.customers.find_one({"tenantId": tenant_id, "email": DEMO_CUSTOMER_EMAIL})

    await db.transactions.delete_many({"tenantId": tenant_id, "source": "demo_seed"})
    order_id = ObjectId()
    await db.transactions.insert_one(
        {
            "_id": order_id,
            "tenantId": tenant_id,
            "transactionNumber": "ORD-DEMO-1001",
            "transactionType": "order",
            "source": "demo_seed",
            "status": "pending",
            "paymentStatus": "unpaid",
            "paymentMethod": "cod",
            "inventoryStatus": "reserved",
            "customerId": customer["_id"] if customer else None,
            "customerUserId": customer_user_id,
            "customerSnapshot": {"name": "Demo Customer", "phone": DEMO_CUSTOMER_PHONE, "email": DEMO_CUSTOMER_EMAIL},
            "items": [
                {"itemId": item_ids[2], "name": "Zinger Burger", "quantity": 1, "unitPrice": 520, "total": 520, "selectedOptions": {}, "selectedVariantId": None}
            ],
            "subtotal": 520,
            "discountTotal": 0,
            "taxTotal": 0,
            "deliveryFee": 150,
            "grandTotal": 670,
            "currency": "PKR",
            "fulfillment": {"type": "delivery", "address": {"line1": "House 12", "city": "Attock", "province": "Punjab"}},
            "notes": "Demo order for final supervisor demo.",
            "internalNotes": "Seeded by Phase 27 demo data script.",
            "statusHistory": [],
            "createdAt": now_utc() - timedelta(hours=2),
            "updatedAt": now_utc() - timedelta(hours=2),
        }
    )
    await db.conversations.delete_many({"tenantId": tenant_id, "source": "demo_seed"})
    await db.conversations.insert_one(
        {
            "tenantId": tenant_id,
            "source": "demo_seed",
            "channel": "website",
            "customerName": "Demo Customer",
            "customerPhone": DEMO_CUSTOMER_PHONE,
            "status": "open",
            "lastMessageAt": now_utc(),
            "messages": [
                {"sender": "customer", "text": "black hoodie large chahiye delivery ke sath", "createdAt": now_utc() - timedelta(minutes=5)},
                {"sender": "assistant", "text": "Black / Large Premium Hoodie available hai. Price 2599 PKR hai. Kya main draft order bana doon?", "createdAt": now_utc() - timedelta(minutes=4)},
            ],
            "createdAt": now_utc() - timedelta(minutes=5),
            "updatedAt": now_utc(),
        }
    )

    await db.qa_demo_runs.delete_many({"tenantId": tenant_id})
    await db.qa_demo_runs.insert_one(
        {
            "tenantId": tenant_id,
            "result": "warn",
            "notes": "Seeded baseline QA run. Re-run from /dashboard/final-qa after local testing.",
            "reviewerName": "Demo Seeder",
            "checkedSteps": [1, 2, 3, 4, 5, 6],
            "qaSummary": {"status": "demo_ready_with_warnings", "percent": 85, "requiredPercent": 90},
            "createdBy": None,
            "createdAt": now_utc(),
        }
    )


async def main() -> None:
    await connect_to_mongo()
    status = await get_mongo_status()
    if not status.get("connected"):
        raise SystemExit("MongoDB is not reachable. Start MongoDB and try again.")
    await seed_modules()
    await seed_business_categories()
    owner_id = await upsert_user(DEMO_OWNER_EMAIL, "Demo Business Owner", DEMO_OWNER_PHONE, "business_owner", DEMO_PASSWORD)
    customer_id = await upsert_user(DEMO_CUSTOMER_EMAIL, "Demo Customer", DEMO_CUSTOMER_PHONE, "customer", DEMO_PASSWORD)
    await upsert_user(DEMO_ADMIN_EMAIL, "Demo Platform Admin", "+923009999999", "business_owner", DEMO_ADMIN_PASSWORD, global_role="admin")
    category_id = await ensure_category()
    tenant_id = await ensure_demo_tenant(owner_id, category_id)
    await enable_modules(tenant_id, owner_id)
    await seed_demo_integrations(tenant_id, owner_id)
    item_ids = await seed_items(tenant_id)
    await seed_business_data(tenant_id, customer_id, item_ids)
    print("Demo data is ready.")
    print(f"Business owner: {DEMO_OWNER_EMAIL} / {DEMO_PASSWORD}")
    print(f"Customer:       {DEMO_CUSTOMER_EMAIL} / {DEMO_PASSWORD}")
    print(f"Admin:          {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")
    print(f"Public site:    /businesses/{DEMO_SLUG}")
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
