from fastapi import APIRouter

from app.api.v1.ai_chat_routes import router as ai_chat_router
from app.api.v1.agent_routes import router as agent_router
from app.api.v1.admin_routes import router as admin_router
from app.api.v1.analytics_routes import router as analytics_router
from app.api.v1.auth_routes import router as auth_router
from app.api.v1.business_notification_routes import router as business_notification_router
from app.api.v1.business_category_routes import router as business_category_router
from app.api.v1.cashier_routes import cashier_router, owner_router as cashier_owner_router
from app.api.v1.customer_auth_routes import router as customer_auth_router
from app.api.v1.customer_portal_routes import router as customer_portal_router
from app.api.v1.customer_routes import router as customer_router
from app.api.v1.custom_field_routes import router as custom_field_router
from app.api.v1.health_routes import router as health_router
from app.api.v1.item_routes import router as item_router
from app.api.v1.knowledge_base_routes import router as knowledge_base_router
from app.api.v1.module_routes import router as module_router
from app.api.v1.onboarding_routes import router as onboarding_router
from app.api.v1.order_import_routes import router as order_import_router
from app.api.v1.payment_routes import router as payment_router
from app.api.v1.payment_gateway_routes import router as payment_gateway_router
from app.api.v1.owner_agent_routes import router as owner_agent_router
from app.api.v1.report_delivery_routes import router as report_delivery_router
from app.api.v1.submission_routes import router as submission_router
from app.api.v1.stripe_routes import router as stripe_router
from app.api.v1.qa_routes import router as qa_router
from app.api.v1.public_website_routes import router as public_website_router
from app.api.v1.report_routes import router as report_router
from app.api.v1.tenant_routes import router as tenant_router
from app.api.v1.transaction_routes import router as transaction_router
from app.api.v1.whatsapp_routes import router as whatsapp_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(admin_router)
api_router.include_router(agent_router)
api_router.include_router(ai_chat_router)
api_router.include_router(analytics_router)
api_router.include_router(auth_router)
api_router.include_router(business_notification_router)
api_router.include_router(customer_auth_router)
api_router.include_router(customer_portal_router)
api_router.include_router(tenant_router)
api_router.include_router(business_category_router)
api_router.include_router(module_router)
api_router.include_router(onboarding_router)
api_router.include_router(owner_agent_router)
api_router.include_router(payment_router)
api_router.include_router(payment_gateway_router)
api_router.include_router(qa_router)
api_router.include_router(report_delivery_router)
api_router.include_router(submission_router)
api_router.include_router(stripe_router)
api_router.include_router(custom_field_router)
api_router.include_router(customer_router)
api_router.include_router(item_router)
api_router.include_router(knowledge_base_router)
api_router.include_router(public_website_router)
api_router.include_router(report_router)
api_router.include_router(cashier_owner_router)
api_router.include_router(cashier_router)
api_router.include_router(order_import_router)
api_router.include_router(transaction_router)
api_router.include_router(whatsapp_router)
