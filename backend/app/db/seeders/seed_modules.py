import logging
from datetime import datetime, timezone

from app.db.mongodb import get_database, get_mongo_status

logger = logging.getLogger(__name__)

ALL_PLANS = ["starter", "growth", "scale"]

DEFAULT_MODULES = [
    {
        "code": "items",
        "name": "Items",
        "description": "Products and services module.",
        "category": "core",
        "apiPrefix": "/items",
        "frontendRoutes": ["/dashboard/items", "/dashboard/items/import"],
        "dependencies": [],
        "availability": {"includedPlans": ALL_PLANS},
        "usageLimits": {
            "starter": {"metricCode": "active_items", "label": "Active items", "limit": 50},
            "growth": {"metricCode": "active_items", "label": "Active items", "limit": 500},
            "scale": {"metricCode": "active_items", "label": "Active items", "limit": None},
        },
    },
    {
        "code": "customers",
        "name": "Customers",
        "description": "Business-side customer records.",
        "category": "core",
        "apiPrefix": "/customers",
        "frontendRoutes": ["/dashboard/customers"],
        "dependencies": [],
        "availability": {"includedPlans": ALL_PLANS},
        "usageLimits": {
            "starter": {"metricCode": "customers", "label": "Customer records", "limit": 200},
            "growth": {"metricCode": "customers", "label": "Customer records", "limit": 2000},
            "scale": {"metricCode": "customers", "label": "Customer records", "limit": None},
        },
    },
    {
        "code": "website_builder",
        "name": "Website Builder",
        "description": "Public business website publishing.",
        "category": "operations",
        "apiPrefix": "/public",
        "frontendRoutes": ["/dashboard/public-website"],
        "dependencies": [],
        "availability": {"includedPlans": ALL_PLANS},
    },
    {
        "code": "customer_portal",
        "name": "Customer Portal",
        "description": "Customer marketplace and order portal.",
        "category": "operations",
        "apiPrefix": "/customer",
        "frontendRoutes": ["/customer/marketplace"],
        "dependencies": ["website_builder", "items"],
        "availability": {"includedPlans": ALL_PLANS},
    },
    {
        "code": "ai_chat",
        "name": "AI Chat",
        "description": "Tenant-aware AI chat, agent tools, RAG, and assisted ordering.",
        "category": "ai",
        "apiPrefix": "/chat",
        "frontendRoutes": ["/dashboard/ai-conversations", "/dashboard/knowledge-base", "/dashboard/agent-tools"],
        "dependencies": ["website_builder"],
        "availability": {"includedPlans": ALL_PLANS},
        "usageLimits": {
            "growth": {"metricCode": "monthly_ai_messages", "label": "Monthly AI chats", "limit": 300},
            "scale": {"metricCode": "monthly_ai_messages", "label": "Monthly AI chats", "limit": None},
        },
    },

    {
        "code": "whatsapp_agent",
        "name": "WhatsApp Agent",
        "description": "Connect a business WhatsApp number so BizXus AI can answer customer queries and prepare order drafts from WhatsApp.",
        "category": "ai",
        "apiPrefix": "/whatsapp",
        "frontendRoutes": ["/dashboard/whatsapp-agent"],
        "dependencies": ["ai_chat"],
        "availability": {"includedPlans": ALL_PLANS},
        "usageLimits": {
            "growth": {"metricCode": "monthly_whatsapp_messages", "label": "Monthly WhatsApp messages", "limit": 300},
            "scale": {"metricCode": "monthly_whatsapp_messages", "label": "Monthly WhatsApp messages", "limit": None},
        },
    },

    {
        "code": "owner_agent",
        "name": "Owner AI Assistant",
        "description": "Owner-side business assistant for summaries, low stock, pending orders, payments, customer chats, and promotion ideas.",
        "category": "ai",
        "apiPrefix": "/owner-agent",
        "frontendRoutes": ["/dashboard/owner-agent"],
        "dependencies": ["ai_chat", "analytics", "reports", "notifications"],
        "availability": {"includedPlans": ALL_PLANS},
        "usageLimits": {
            "scale": {"metricCode": "monthly_owner_agent_messages", "label": "Monthly owner assistant messages", "limit": None}
        },
    },
    {
        "code": "analytics",
        "name": "Analytics",
        "description": "Basic business dashboard analytics.",
        "category": "operations",
        "apiPrefix": "/analytics",
        "frontendRoutes": ["/dashboard/analytics"],
        "dependencies": [],
        "availability": {"includedPlans": ALL_PLANS},
    },
    {
        "code": "payments",
        "name": "Payments",
        "description": "COD, manual, and mock payment flows.",
        "category": "operations",
        "apiPrefix": "/payments",
        "frontendRoutes": ["/dashboard/payments"],
        "dependencies": ["customer_portal"],
        "availability": {"includedPlans": ALL_PLANS},
    },
    {
        "code": "cashier",
        "name": "Cashier / POS",
        "description": "In-store counter sales: owner-managed cashier logins, manual order entry, printable receipts, and historical order sheet import.",
        "category": "operations",
        "apiPrefix": "/cashier",
        "frontendRoutes": ["/dashboard/cashiers", "/dashboard/orders/import", "/cashier"],
        "dependencies": ["items"],
        "availability": {"includedPlans": ALL_PLANS},
    },
    {
        "code": "reports",
        "name": "Reports",
        "description": "Reports and business insights.",
        "category": "operations",
        "apiPrefix": "/reports",
        "frontendRoutes": ["/dashboard/reports"],
        "dependencies": ["analytics"],
        "availability": {"includedPlans": ALL_PLANS},
    },
    {
        "code": "admin",
        "name": "Admin",
        "description": "Platform administration tools.",
        "category": "admin",
        "apiPrefix": "/admin",
        "frontendRoutes": ["/admin"],
        "availability": {"includedPlans": ALL_PLANS},
    },
    {
        "code": "notifications",
        "name": "Notifications",
        "description": "In-app and integration-ready notifications.",
        "category": "operations",
        "apiPrefix": "/notifications",
        "frontendRoutes": ["/dashboard/notifications"],
        "dependencies": [],
        "availability": {"includedPlans": ALL_PLANS},
    },
]


async def seed_modules() -> None:
    status = await get_mongo_status()
    if not status["connected"]:
        logger.warning("Skipping module seed because MongoDB is not connected.")
        return

    db = get_database()
    now = datetime.now(timezone.utc)
    for module in DEFAULT_MODULES:
        await db.modules.update_one(
            {"code": module["code"]},
            {
                "$set": {**module, "updatedAt": now},
                "$setOnInsert": {
                    "permissions": [],
                    "configSchema": {},
                    "aiTools": [],
                    "isActive": True,
                    "createdAt": now,
                },
            },
            upsert=True,
        )
    logger.info("Default modules are ready.")
