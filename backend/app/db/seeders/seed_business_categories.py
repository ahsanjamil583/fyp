import logging
from datetime import datetime, timezone

from app.db.mongodb import get_database, get_mongo_status

logger = logging.getLogger(__name__)

DEFAULT_BUSINESS_CATEGORIES = [
    {
        "name": "Other Business",
        "slug": "other-business",
        "description": "Flexible starter category for businesses that do not match a predefined preset yet.",
        "icon": "briefcase",
        "suggestedModules": ["website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers understand the business, available offerings, and how to contact or order from it.",
            "safetyNotes": "Stay grounded in tenant data and ask clarifying questions when business offerings are unclear.",
        },
        "aiPromptFragments": [
            "Adapt to the tenant's actual offerings instead of assuming a fixed business model.",
            "Ask clarifying questions when product, service, or fulfillment details are missing.",
        ],
        "websiteHints": {
            "recommendedTemplate": "service",
            "recommendedPrimaryColor": "#334155",
            "heroStyle": "general-purpose",
        },
        "fulfillmentHints": {
            "defaultMode": "custom",
            "supportsDelivery": True,
            "supportsPickup": True,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track which offerings generate the most interest.",
            "Watch repeat customer behavior and inquiry volume.",
            "Review which channels lead to the most conversions.",
        ],
    },
    {
        "name": "Restaurant",
        "slug": "restaurant",
        "description": "Food business with menu-style products and customer ordering.",
        "icon": "utensils",
        "suggestedModules": ["items", "website_builder", "customer_portal", "ai_chat", "analytics", "payments", "reports", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers browse food items and place confirmed orders.",
            "safetyNotes": "Always confirm order items and quantities before creating an order.",
        },
        "aiPromptFragments": [
            "Keep replies short, friendly, and order-focused.",
            "Highlight menu discovery, pricing, and availability clearly.",
        ],
        "websiteHints": {
            "recommendedTemplate": "catalog",
            "recommendedPrimaryColor": "#DC2626",
            "heroStyle": "menu-first",
        },
        "fulfillmentHints": {
            "defaultMode": "delivery_or_pickup",
            "supportsDelivery": True,
            "supportsPickup": True,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track top-selling menu items daily.",
            "Monitor low-stock ingredients or high-demand products.",
            "Watch repeat customer ordering behavior.",
        ],
    },
    {
        "name": "Retail Store",
        "slug": "retail-store",
        "description": "General retail business with sellable products.",
        "icon": "shopping-bag",
        "suggestedModules": ["items", "customers", "website_builder", "customer_portal", "ai_chat", "analytics"],
        "aiHints": {
            "businessPurpose": "Help customers find products, prices, and availability.",
            "safetyNotes": "Do not promise stock without checking item data.",
        },
        "aiPromptFragments": [
            "Guide customers toward matching products and available stock.",
            "Emphasize product discovery, filters, and availability.",
        ],
        "websiteHints": {
            "recommendedTemplate": "catalog",
            "recommendedPrimaryColor": "#2563EB",
            "heroStyle": "catalog-first",
        },
        "fulfillmentHints": {
            "defaultMode": "pickup_or_delivery",
            "supportsDelivery": True,
            "supportsPickup": True,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track best-selling products by category.",
            "Watch low-stock items and reorder pressure.",
            "Monitor conversion from browsing to orders.",
        ],
    },
    {
        "name": "Pharmacy",
        "slug": "pharmacy",
        "description": "Medicine and health retail business with stock-sensitive catalog management.",
        "icon": "pill",
        "suggestedModules": ["items", "customers", "website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers find products, availability, and store contact information.",
            "safetyNotes": "Do not provide medical diagnosis. Encourage pharmacist or doctor consultation where needed.",
        },
        "aiPromptFragments": [
            "Stay careful with health-related wording and avoid diagnosis.",
            "Focus on product availability, store information, and safe next-step guidance.",
        ],
        "websiteHints": {
            "recommendedTemplate": "catalog",
            "recommendedPrimaryColor": "#059669",
            "heroStyle": "trust-first",
        },
        "fulfillmentHints": {
            "defaultMode": "pickup_or_delivery",
            "supportsDelivery": True,
            "supportsPickup": True,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Monitor fast-moving stock and refill pressure.",
            "Track repeat demand for common medicines and wellness items.",
            "Review customer inquiries for unavailable products.",
        ],
    },
    {
        "name": "Clinic",
        "slug": "clinic",
        "description": "Clinic category using customers and items-as-services for the MVP.",
        "icon": "stethoscope",
        "suggestedModules": ["customers", "items", "website_builder", "customer_portal", "ai_chat"],
        "aiHints": {
            "businessPurpose": "Provide general clinic service information.",
            "safetyNotes": "Do not provide medical diagnosis. Ask customers to contact the clinic for medical advice.",
        },
        "aiPromptFragments": [
            "Stay informative, careful, and non-diagnostic.",
            "Encourage direct clinic contact for medical decisions.",
        ],
        "websiteHints": {
            "recommendedTemplate": "service",
            "recommendedPrimaryColor": "#0F766E",
            "heroStyle": "trust-first",
        },
        "fulfillmentHints": {
            "defaultMode": "in_person_service",
            "supportsDelivery": False,
            "supportsPickup": False,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track service inquiry volume.",
            "Monitor repeat patient/customer interactions.",
            "Review high-demand services for scheduling expansion.",
        ],
    },
    {
        "name": "Salon and Spa",
        "slug": "salon-and-spa",
        "description": "Beauty, salon, and grooming businesses offering services and packages.",
        "icon": "sparkles",
        "suggestedModules": ["items", "customers", "website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers explore services, prices, and contact information.",
            "safetyNotes": "Do not promise appointment times unless scheduling support exists.",
        },
        "aiPromptFragments": [
            "Treat most offerings as services unless the tenant data says otherwise.",
            "Encourage direct contact for scheduling details when needed.",
        ],
        "websiteHints": {
            "recommendedTemplate": "service",
            "recommendedPrimaryColor": "#DB2777",
            "heroStyle": "experience-first",
        },
        "fulfillmentHints": {
            "defaultMode": "in_person_service",
            "supportsDelivery": False,
            "supportsPickup": False,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track most requested services and add-on opportunities.",
            "Review repeat customer patterns.",
            "Monitor inquiries that could justify future appointment support.",
        ],
    },
    {
        "name": "Bakery and Sweets",
        "slug": "bakery-and-sweets",
        "description": "Bakeries, sweet shops, and dessert-focused businesses with order-friendly menus.",
        "icon": "cake-slice",
        "suggestedModules": ["items", "website_builder", "customer_portal", "ai_chat", "analytics", "payments", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers browse baked items, prices, and order quantities.",
            "safetyNotes": "Always confirm item quantities and availability before order confirmation.",
        },
        "aiPromptFragments": [
            "Support menu browsing and quantity-based ordering clearly.",
            "Call out availability-sensitive or daily-fresh items when relevant.",
        ],
        "websiteHints": {
            "recommendedTemplate": "catalog",
            "recommendedPrimaryColor": "#C2410C",
            "heroStyle": "showcase-products",
        },
        "fulfillmentHints": {
            "defaultMode": "pickup_or_delivery",
            "supportsDelivery": True,
            "supportsPickup": True,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track top-selling daily items.",
            "Monitor seasonal demand spikes.",
            "Watch order sizes and repeat purchase trends.",
        ],
    },
    {
        "name": "Electronics Shop",
        "slug": "electronics-shop",
        "description": "Electronics and gadgets businesses with product catalogs and stock-aware sales.",
        "icon": "monitor-smartphone",
        "suggestedModules": ["items", "customers", "website_builder", "customer_portal", "ai_chat", "analytics", "reports"],
        "aiHints": {
            "businessPurpose": "Help customers compare products, pricing, and stock availability.",
            "safetyNotes": "Do not promise warranty terms unless they are present in tenant data.",
        },
        "aiPromptFragments": [
            "Help compare models, prices, and availability where data exists.",
            "Stay grounded in actual catalog data and avoid assumptions about specifications.",
        ],
        "websiteHints": {
            "recommendedTemplate": "catalog",
            "recommendedPrimaryColor": "#1D4ED8",
            "heroStyle": "compare-and-shop",
        },
        "fulfillmentHints": {
            "defaultMode": "pickup_or_delivery",
            "supportsDelivery": True,
            "supportsPickup": True,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track most viewed versus most ordered products.",
            "Monitor low-stock high-value items.",
            "Review category-level sales performance.",
        ],
    },
    {
        "name": "Clothing and Fashion",
        "slug": "clothing-and-fashion",
        "description": "Fashion, clothing, and apparel businesses with visual product catalogs.",
        "icon": "shirt",
        "suggestedModules": ["items", "website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers browse styles, products, and prices.",
            "safetyNotes": "Do not assume sizes or variants unless they are stored in the catalog.",
        },
        "aiPromptFragments": [
            "Focus on discovery, style categories, and available products.",
            "Avoid inventing size, color, or variant details that are not in the data.",
        ],
        "websiteHints": {
            "recommendedTemplate": "catalog",
            "recommendedPrimaryColor": "#7C3AED",
            "heroStyle": "visual-merchandising",
        },
        "fulfillmentHints": {
            "defaultMode": "pickup_or_delivery",
            "supportsDelivery": True,
            "supportsPickup": True,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track high-interest product groups.",
            "Review repeat customer behavior by season.",
            "Watch which categories drive the most conversions.",
        ],
    },
    {
        "name": "Repair and Maintenance",
        "slug": "repair-and-maintenance",
        "description": "Repair shops and maintenance services for devices, appliances, vehicles, or equipment.",
        "icon": "wrench",
        "suggestedModules": ["customers", "items", "website_builder", "ai_chat", "analytics", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers understand available services and how to request support.",
            "safetyNotes": "Do not promise exact repair results or timelines unless explicitly provided.",
        },
        "aiPromptFragments": [
            "Treat most offerings as service requests or diagnostic inquiries.",
            "Ask clarifying questions about the issue when service details are unclear.",
        ],
        "websiteHints": {
            "recommendedTemplate": "service",
            "recommendedPrimaryColor": "#475569",
            "heroStyle": "trust-and-service",
        },
        "fulfillmentHints": {
            "defaultMode": "in_person_service",
            "supportsDelivery": False,
            "supportsPickup": True,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track most common repair request types.",
            "Monitor repeat service customers.",
            "Review inquiry volume versus completed jobs.",
        ],
    },
    {
        "name": "Education and Training",
        "slug": "education-and-training",
        "description": "Tuition centers, academies, and trainers offering educational services.",
        "icon": "graduation-cap",
        "suggestedModules": ["customers", "items", "website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers understand available classes, programs, and fees.",
            "safetyNotes": "Do not promise schedules or certification outcomes unless provided in tenant data.",
        },
        "aiPromptFragments": [
            "Treat offerings as programs, classes, or learning services.",
            "Encourage direct follow-up for schedule-specific questions if needed.",
        ],
        "websiteHints": {
            "recommendedTemplate": "service",
            "recommendedPrimaryColor": "#0F766E",
            "heroStyle": "program-first",
        },
        "fulfillmentHints": {
            "defaultMode": "in_person_service",
            "supportsDelivery": False,
            "supportsPickup": False,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track most requested programs or classes.",
            "Monitor inquiry-to-enrollment intent.",
            "Review retention or repeat engagement patterns.",
        ],
    },
    {
        "name": "Gym and Fitness",
        "slug": "gym-and-fitness",
        "description": "Gyms, fitness studios, and wellness training businesses focused on memberships and services.",
        "icon": "dumbbell",
        "suggestedModules": ["customers", "items", "website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers understand fitness programs, services, and contact information.",
            "safetyNotes": "Do not provide medical or injury advice. Suggest direct staff contact for health concerns.",
        },
        "aiPromptFragments": [
            "Treat offerings as training services, classes, or memberships unless the tenant data says otherwise.",
            "Stay informative and avoid health diagnosis or medical claims.",
        ],
        "websiteHints": {
            "recommendedTemplate": "service",
            "recommendedPrimaryColor": "#EA580C",
            "heroStyle": "energy-first",
        },
        "fulfillmentHints": {
            "defaultMode": "in_person_service",
            "supportsDelivery": False,
            "supportsPickup": False,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track inquiry interest by program type.",
            "Monitor repeat engagement from active members.",
            "Review which services attract the most attention.",
        ],
    },
    {
        "name": "Professional Services",
        "slug": "professional-services",
        "description": "Consultants, agencies, freelancers, and office-based service businesses.",
        "icon": "briefcase-business",
        "suggestedModules": ["website_builder", "customers", "ai_chat", "analytics", "reports", "notifications"],
        "aiHints": {
            "businessPurpose": "Help customers understand services, pricing approach, and how to get in touch.",
            "safetyNotes": "Do not guarantee outcomes, quotes, or project terms without stored business data.",
        },
        "aiPromptFragments": [
            "Focus on service discovery, lead capture, and clarity of offering.",
            "Ask clarifying questions when services need custom scoping.",
        ],
        "websiteHints": {
            "recommendedTemplate": "service",
            "recommendedPrimaryColor": "#0F172A",
            "heroStyle": "credibility-first",
        },
        "fulfillmentHints": {
            "defaultMode": "consultation",
            "supportsDelivery": False,
            "supportsPickup": False,
            "supportsInPerson": True,
        },
        "analyticsSuggestions": [
            "Track lead and inquiry volume.",
            "Monitor which services generate the strongest interest.",
            "Review repeat client engagement opportunities.",
        ],
    },
]

ESSENTIAL_BUSINESS_CATEGORIES = [
    {
        "name": "Beauty / Salon",
        "slug": "beauty-salon",
        "description": "Beauty, salon, spa, and personal care businesses with service bookings.",
        "icon": "sparkles",
        "suggestedModules": ["website_builder", "customer_portal", "ai_chat", "bookings", "analytics", "notifications"],
        "websiteHints": {"recommendedTemplate": "service", "recommendedPrimaryColor": "#DB2777", "heroStyle": "visual-service"},
        "fulfillmentHints": {"defaultMode": "in_person_service", "supportsDelivery": False, "supportsPickup": False, "supportsInPerson": True},
        "analyticsSuggestions": ["Track bookings by service.", "Monitor repeat customers.", "Review appointment inquiries."],
    },
    {
        "name": "Electronics",
        "slug": "electronics",
        "description": "Electronics, accessories, and gadget retail with catalog and stock tracking.",
        "icon": "cpu",
        "suggestedModules": ["items", "customers", "website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "websiteHints": {"recommendedTemplate": "catalog", "recommendedPrimaryColor": "#0F172A", "heroStyle": "catalog-first"},
        "fulfillmentHints": {"defaultMode": "pickup_or_delivery", "supportsDelivery": True, "supportsPickup": True, "supportsInPerson": True},
        "analyticsSuggestions": ["Track best-selling products.", "Watch low-stock accessories.", "Monitor product inquiries."],
    },
    {
        "name": "Fashion / Clothing",
        "slug": "fashion-clothing",
        "description": "Clothing, fashion, and boutique businesses with variants like size and color.",
        "icon": "shirt",
        "suggestedModules": ["items", "customers", "website_builder", "customer_portal", "ai_chat", "analytics", "payments"],
        "websiteHints": {"recommendedTemplate": "catalog", "recommendedPrimaryColor": "#7C3AED", "heroStyle": "visual-catalog"},
        "fulfillmentHints": {"defaultMode": "pickup_or_delivery", "supportsDelivery": True, "supportsPickup": True, "supportsInPerson": True},
        "analyticsSuggestions": ["Track size and color demand.", "Watch low-stock variants.", "Monitor repeat customers."],
    },
    {
        "name": "General Business",
        "slug": "general-business",
        "description": "Flexible category for businesses that need a simple website, customer chat, and operations setup.",
        "icon": "briefcase",
        "suggestedModules": ["website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "websiteHints": {"recommendedTemplate": "default", "recommendedPrimaryColor": "#2563EB", "heroStyle": "general-purpose"},
        "fulfillmentHints": {"defaultMode": "custom", "supportsDelivery": True, "supportsPickup": True, "supportsInPerson": True},
        "analyticsSuggestions": ["Track inquiries.", "Monitor customer engagement.", "Review conversion channels."],
    },
    {
        "name": "Grocery",
        "slug": "grocery",
        "description": "Grocery, mart, and daily essentials businesses with stock-sensitive product catalogs.",
        "icon": "shopping-cart",
        "suggestedModules": ["items", "customers", "website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "websiteHints": {"recommendedTemplate": "catalog", "recommendedPrimaryColor": "#16A34A", "heroStyle": "catalog-first"},
        "fulfillmentHints": {"defaultMode": "pickup_or_delivery", "supportsDelivery": True, "supportsPickup": True, "supportsInPerson": True},
        "analyticsSuggestions": ["Track fast-moving items.", "Watch low-stock essentials.", "Monitor order frequency."],
    },
    {
        "name": "Services",
        "slug": "services",
        "description": "Professional and local service businesses with inquiries, bookings, and lead capture.",
        "icon": "handshake",
        "suggestedModules": ["website_builder", "customer_portal", "ai_chat", "analytics", "notifications"],
        "websiteHints": {"recommendedTemplate": "service", "recommendedPrimaryColor": "#0891B2", "heroStyle": "service-first"},
        "fulfillmentHints": {"defaultMode": "consultation", "supportsDelivery": False, "supportsPickup": False, "supportsInPerson": True},
        "analyticsSuggestions": ["Track inquiry volume.", "Monitor service demand.", "Review response performance."],
    },
    {
        "name": "Tailor",
        "slug": "tailor",
        "description": "Tailoring, alteration, stitching, and custom clothing services.",
        "icon": "scissors",
        "suggestedModules": ["customers", "website_builder", "customer_portal", "ai_chat", "bookings", "analytics"],
        "websiteHints": {"recommendedTemplate": "service", "recommendedPrimaryColor": "#92400E", "heroStyle": "custom-service"},
        "fulfillmentHints": {"defaultMode": "in_person_service", "supportsDelivery": False, "supportsPickup": True, "supportsInPerson": True},
        "analyticsSuggestions": ["Track stitching requests.", "Monitor repeat customers.", "Review pickup and delivery needs."],
    },
]


def default_business_categories() -> list[dict]:
    categories = {category["slug"]: category for category in DEFAULT_BUSINESS_CATEGORIES}
    for category in ESSENTIAL_BUSINESS_CATEGORIES:
        categories.setdefault(category["slug"], category)
    return list(categories.values())


# Mirrors the field list update_category accepts (business_category_service). A field an
# admin can change must not be written back by the seeder on the next boot.
_ADMIN_EDITABLE_CATEGORY_FIELDS = frozenset(
    {
        "name",
        "description",
        "icon",
        "isActive",
        "suggestedModules",
        "defaultCustomFields",
        "aiHints",
        "aiPromptFragments",
        "websiteHints",
        "fulfillmentHints",
        "analyticsSuggestions",
    }
)


async def seed_business_categories() -> None:
    status = await get_mongo_status()
    if not status["connected"]:
        logger.warning("Skipping category seed because MongoDB is not connected.")
        return

    db = get_database()
    now = datetime.now(timezone.utc)
    for category in default_business_categories():
        await db.business_categories.update_one(
            {"slug": category["slug"]},
            {
                # Every field a platform admin can edit is seeded on insert only.
                # Protecting `isActive` alone still let a restart overwrite an edited
                # name, description, icon, suggested modules or AI hints, which is the
                # same bug on a different field. `slug` stays in $set because it is the
                # match key and update_category enforces its uniqueness separately.
                "$set": {**{key: value for key, value in category.items() if key not in _ADMIN_EDITABLE_CATEGORY_FIELDS}, "updatedAt": now},
                "$setOnInsert": {
                    "defaultCustomFields": [],
                    "createdAt": now,
                    "isActive": True,
                    **{key: value for key, value in category.items() if key in _ADMIN_EDITABLE_CATEGORY_FIELDS and key != "isActive"},
                },
            },
            upsert=True,
        )
    logger.info("Default business categories are ready.")
