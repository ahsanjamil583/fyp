import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.ai.agents.orchestrator_agent import AGENT_TOOL_CATALOG, run_customer_agent
from app.ai.agents.tools import summarize_notification_tool, summarize_payment_tool, summarize_report_tool, summarize_stock_tool
from app.schemas.agent_schema import AgentPreviewRequest


class Phase23AgentToolLayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_customer_agent_exposes_complete_tool_trace(self):
        tenant_id = ObjectId()
        item_id = ObjectId()
        tenant = {
            "_id": tenant_id,
            "name": "Demo Bazaar",
            "settings": {
                "paymentSettings": {
                    "cod": {"enabled": True},
                    "manual": {"enabled": True},
                    "jazzcash": {"enabled": True},
                }
            },
        }
        item = {
            "_id": item_id,
            "tenantId": tenant_id,
            "name": "Premium Hoodie",
            "description": "Warm black cotton hoodie",
            "price": 2499,
            "currency": "PKR",
            "itemType": "product",
            "isSellable": True,
            "isBookable": False,
            "isStockTracked": True,
            "stock": {"quantity": 20, "reservedQuantity": 0, "lowStockThreshold": 3},
            "tags": ["hoodie", "black", "winter"],
            "variants": [
                {
                    "name": "Black / Large",
                    "sku": "HOODIE-BLK-L",
                    "price": 2599,
                    "stockQuantity": 6,
                    "reservedQuantity": 0,
                    "lowStockThreshold": 2,
                    "isActive": True,
                    "optionValues": {"color": "Black", "size": "Large"},
                }
            ],
        }
        knowledge = [{"id": str(ObjectId()), "title": "Delivery Policy", "sourceType": "owner_text", "excerpt": "Same-day delivery in Attock.", "confidence": 0.91}]

        with (
            patch("app.ai.agents.orchestrator_agent.hydrate_tenant_category", new=AsyncMock(return_value={**tenant, "categoryConfig": {"name": "General Commerce"}})),
            patch("app.ai.agents.orchestrator_agent.retrieve_sellable_items", new=AsyncMock(return_value=[item])),
            patch("app.ai.agents.orchestrator_agent.retrieve_tenant_knowledge", new=AsyncMock(return_value=knowledge)),
            patch("app.ai.agents.tools.generate_openai_response", new=AsyncMock(return_value=None)),
            patch("app.ai.agents.tools.generate_groq_response", new=AsyncMock(return_value=None)),
        ):
            result = await run_customer_agent(tenant, "2 black large hoodie order kar do", channel="whatsapp")

        tools = [event["tool"] for event in result["toolCalls"]]
        for expected_tool in [
            "category_context_loader",
            "language_detector",
            "safety_guard",
            "catalog_search_tool",
            "intent_classifier",
            "hybrid_rag_retriever",
            "draft_order_tool",
            "stock_tool",
            "payment_tool",
            "report_tool",
            "notification_tool",
            "response_generator",
            "localization_evaluator",
        ]:
            self.assertIn(expected_tool, tools)

        self.assertTrue(result["draftOrder"]["canConfirm"])
        self.assertEqual(result["draftOrder"]["items"][0]["selectedVariantName"], "Black / Large")
        self.assertEqual(result["meta"]["agentLayer"], "phase_24_smart_customer_ordering")
        report_event = next(event for event in result["toolCalls"] if event["tool"] == "report_tool")
        self.assertEqual(report_event["status"], "skipped")
        self.assertFalse(report_event["output"]["availableInThisChannel"])

    async def test_customer_agent_rejects_cross_category_item_request(self):
        tenant = {"_id": ObjectId(), "name": "Burger House", "settings": {}}

        with (
            patch("app.ai.agents.orchestrator_agent.hydrate_tenant_category", new=AsyncMock(return_value={**tenant, "categoryConfig": {"name": "Restaurant"}})),
            patch("app.ai.agents.orchestrator_agent.retrieve_sellable_items", new=AsyncMock(return_value=[])),
            patch("app.ai.agents.orchestrator_agent.retrieve_tenant_knowledge", new=AsyncMock(return_value=[])),
            patch("app.ai.agents.tools.generate_openai_response", new=AsyncMock(return_value=None)),
            patch("app.ai.agents.tools.generate_groq_response", new=AsyncMock(return_value=None)),
        ):
            result = await run_customer_agent(tenant, "Black hoodie available hai?", channel="whatsapp")

        self.assertIn("Restaurant", result["reply"])
        self.assertIn("hoodie", result["reply"])
        self.assertIn("burgers", result["reply"])
        self.assertFalse(result["draftOrder"])

    async def test_customer_agent_answers_policy_from_knowledge_base_before_catalog_fallback(self):
        tenant = {"_id": ObjectId(), "name": "Demo Fashion", "settings": {}}
        knowledge = [
            {
                "id": str(ObjectId()),
                "title": "Delivery Policy",
                "sourceType": "owner_text",
                "excerpt": "Delivery is available in Attock, Wah Cantt, and Taxila. Delivery charges are PKR 200. Orders above PKR 5000 get free delivery.",
                "confidence": 0.82,
                "matchType": "hybrid",
            }
        ]

        with (
            patch("app.ai.agents.orchestrator_agent.hydrate_tenant_category", new=AsyncMock(return_value={**tenant, "categoryConfig": {"name": "Fashion"}})),
            patch("app.ai.agents.orchestrator_agent.retrieve_sellable_items", new=AsyncMock(return_value=[])),
            patch("app.ai.agents.orchestrator_agent.retrieve_tenant_knowledge", new=AsyncMock(return_value=knowledge)),
            patch("app.ai.agents.tools.generate_openai_response", new=AsyncMock(return_value=None)),
            patch("app.ai.agents.tools.generate_groq_response", new=AsyncMock(return_value=None)),
        ):
            result = await run_customer_agent(tenant, "Delivery Wah Cantt mein hoti hai?", channel="customer_portal")

        self.assertIn("Wah Cantt", result["reply"])
        self.assertIn("PKR 200", result["reply"])
        self.assertEqual(result["meta"]["knowledgeCount"], 1)

    async def test_short_followup_uses_previous_customer_context_for_draft(self):
        tenant_id = ObjectId()
        item_id = ObjectId()
        tenant = {"_id": tenant_id, "name": "Shoe Store", "settings": {}}
        item = {
            "_id": item_id,
            "tenantId": tenant_id,
            "name": "White Sneakers",
            "description": "White sneakers for daily wear",
            "price": 4500,
            "currency": "PKR",
            "itemType": "product",
            "isSellable": True,
            "isBookable": False,
            "isStockTracked": True,
            "stock": {"quantity": 8, "reservedQuantity": 0, "lowStockThreshold": 2},
            "tags": ["white", "sneakers", "shoes"],
            "variants": [
                {
                    "name": "White / 42",
                    "sku": "SNK-WHT-42",
                    "price": 4500,
                    "stockQuantity": 5,
                    "reservedQuantity": 0,
                    "lowStockThreshold": 2,
                    "isActive": True,
                    "optionValues": {"color": "White", "size": "42"},
                }
            ],
        }
        recent_messages = [
            {"sender": "customer", "messageText": "White sneakers size 42 available hai?"},
            {"sender": "ai", "messageText": "Ji available hai. Order banana hai?"},
            {"sender": "customer", "messageText": "g bana do"},
        ]

        with (
            patch("app.ai.agents.orchestrator_agent.hydrate_tenant_category", new=AsyncMock(return_value={**tenant, "categoryConfig": {"name": "Fashion"}})),
            patch("app.ai.agents.orchestrator_agent.retrieve_sellable_items", new=AsyncMock(return_value=[item])),
            patch("app.ai.agents.orchestrator_agent.retrieve_tenant_knowledge", new=AsyncMock(return_value=[])),
            patch("app.ai.agents.tools.generate_openai_response", new=AsyncMock(return_value=None)),
            patch("app.ai.agents.tools.generate_groq_response", new=AsyncMock(return_value=None)),
        ):
            result = await run_customer_agent(tenant, "g bana do", recent_messages=recent_messages, channel="customer_portal")

        self.assertTrue(result["draftOrder"]["items"])
        self.assertEqual(result["draftOrder"]["items"][0]["name"], "White Sneakers")
        self.assertEqual(result["draftOrder"]["items"][0]["selectedVariantName"], "White / 42")
        self.assertIn("Draft", result["reply"])

    def test_tool_catalog_lists_phase23_operational_tools(self):
        catalog_tools = {tool["tool"] for tool in AGENT_TOOL_CATALOG}
        for expected_tool in {"hybrid_rag_retriever", "catalog_search_tool", "draft_order_tool", "stock_tool", "payment_tool", "report_tool", "notification_tool"}:
            self.assertIn(expected_tool, catalog_tools)

    def test_tool_summaries_are_side_effect_free(self):
        draft = {
            "items": [{"name": "Burger", "stockSnapshot": {"tracked": True, "available": True, "remainingAfter": 2, "lowStockThreshold": 3}}],
            "pricing": {"total": 670},
            "canConfirm": True,
            "status": "awaiting_confirmation",
        }
        tenant = {"settings": {"paymentSettings": {"cod": {"enabled": True}, "manual": {"enabled": False}}}}

        stock = summarize_stock_tool(draft, [])
        payment = summarize_payment_tool(tenant, draft)
        reports = summarize_report_tool("website", {"intent": "place_order"})
        notifications = summarize_notification_tool("website", draft)

        self.assertEqual(stock["trackedLineCount"], 1)
        self.assertEqual(stock["lowStockLines"][0]["name"], "Burger")
        self.assertEqual(payment["paymentStatus"], "not_collected_by_agent")
        self.assertEqual(payment["enabledMethods"], ["cod"])
        self.assertFalse(reports["availableInThisChannel"])
        self.assertTrue(notifications["willNotifyOnConfirmation"])

    def test_preview_request_rejects_unknown_channel(self):
        with self.assertRaises(ValueError):
            AgentPreviewRequest(messageText="test", channel="admin_console")


if __name__ == "__main__":
    unittest.main()
