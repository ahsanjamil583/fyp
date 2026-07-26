import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.services.owner_agent_service import get_owner_agent_insights
from app.services.report_delivery_service import deliver_daily_summary, run_scheduled_report_delivery


class Phase26ReportsOwnerAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_agent_insights_counts_partially_paid_transactions(self):
        tenant_id = ObjectId()
        tenant = {"_id": tenant_id, "name": "Demo Biz", "slug": "demo-biz"}
        fake_aggregate_cursor = SimpleNamespace(to_list=AsyncMock(return_value=[{"_id": None, "amount": 200, "count": 1}]))
        fake_db = SimpleNamespace(
            transactions=SimpleNamespace(
                count_documents=AsyncMock(return_value=3),
                aggregate=lambda pipeline: fake_aggregate_cursor,
            ),
            business_notifications=SimpleNamespace(count_documents=AsyncMock(return_value=2)),
            conversations=SimpleNamespace(count_documents=AsyncMock(return_value=4)),
        )
        analytics_summary = {
            "summary": {"totalTransactions": 3, "totalOrders": 2, "todayOrders": 1},
            "revenue": {"grossRevenue": 5000, "averageOrderValue": 2500},
            "lowStockItems": [{"name": "Hoodie", "stock": {"quantity": 2}}],
            "topItems": [{"name": "Burger"}],
            "recentTransactions": [],
            "dashboardSummary": "ok",
        }

        with (
            patch("app.services.owner_agent_service._get_owner_agent_access", AsyncMock(return_value=(tenant_id, tenant))),
            patch("app.services.owner_agent_service.get_database", return_value=fake_db),
            patch("app.services.owner_agent_service.sync_low_stock_notifications", AsyncMock()),
            patch("app.services.owner_agent_service.get_analytics_summary", AsyncMock(return_value=analytics_summary)),
            patch("app.services.owner_agent_service.get_daily_summary", AsyncMock(return_value={})),
        ):
            result = await get_owner_agent_insights(str(tenant_id), {"_id": ObjectId()})

        unpaid_card = next(card for card in result["cards"] if card["label"] == "Unpaid Amount")
        self.assertEqual(unpaid_card["value"], "PKR 200")

    async def test_daily_report_delivery_logs_delivered_status(self):
        tenant_id = ObjectId()
        tenant = {"_id": tenant_id, "name": "Demo Biz", "slug": "demo-biz", "contact": {"phone": "03001234567"}}
        settings_doc = {
            "tenantId": tenant_id,
            "enabled": True,
            "whatsappEnabled": True,
            "smsEnabled": True,
            "deliveryTime": "21:00",
            "timezone": "Asia/Karachi",
            "whatsappRecipient": "03001234567",
            "smsRecipient": "03001234567",
            "languageMode": "english",
            "includeLowStock": True,
            "includeTopItems": True,
            "includeRecentOrders": True,
        }
        fake_db = SimpleNamespace(
            report_delivery_settings=SimpleNamespace(
                find_one=AsyncMock(return_value=settings_doc),
                update_one=AsyncMock(),
            )
        )
        summary = {
            "summaryDate": "2026-07-02",
            "metrics": {"newTransactions": 4, "newOrders": 3, "grossRevenue": 5000, "averageOrderValue": 1250},
            "topItems": [{"name": "Burger", "quantity": 5, "revenue": 2500}],
            "lowStockItems": [{"name": "Sauce"}],
            "recentTransactions": [{"transactionNumber": "ORD-1", "status": "completed"}],
        }
        fake_logs = [
            {"deliveryStatus": "dry_run", "channel": "whatsapp", "summaryDate": "2026-07-02"},
            {"deliveryStatus": "dry_run", "channel": "sms", "summaryDate": "2026-07-02"},
        ]

        with (
            patch("app.services.report_delivery_service._get_delivery_access", AsyncMock(return_value=(tenant_id, tenant))),
            patch("app.services.report_delivery_service.get_database", return_value=fake_db),
            patch("app.services.report_delivery_service.generate_daily_summary", AsyncMock(return_value=summary)),
            patch("app.services.report_delivery_service._deliver_channel", AsyncMock(side_effect=fake_logs)),
            patch("app.services.report_delivery_service.create_business_notification", AsyncMock()),
        ):
            result = await deliver_daily_summary(
                str(tenant_id),
                SimpleNamespace(summaryDate="2026-07-02", channels=["whatsapp", "sms"], dryRun=True),
                {"_id": ObjectId()},
            )

        self.assertEqual(result["deliveryStatus"], "delivered")
        self.assertEqual(len(result["logs"]), 2)
        fake_db.report_delivery_settings.update_one.assert_awaited_once()

    async def test_scheduled_report_delivery_skips_when_disabled(self):
        tenant_id = ObjectId()
        tenant = {"_id": tenant_id, "name": "Demo Biz", "slug": "demo-biz"}
        fake_db = SimpleNamespace(
            report_delivery_settings=SimpleNamespace(
                find_one=AsyncMock(return_value={"tenantId": tenant_id, "enabled": False, "whatsappEnabled": False, "smsEnabled": False}),
            )
        )

        with (
            patch("app.services.report_delivery_service._get_delivery_access", AsyncMock(return_value=(tenant_id, tenant))),
            patch("app.services.report_delivery_service.get_database", return_value=fake_db),
        ):
            result = await run_scheduled_report_delivery(
                str(tenant_id),
                SimpleNamespace(summaryDate="2026-07-02", dryRun=True),
                {"_id": ObjectId()},
            )

        self.assertEqual(result["deliveryStatus"], "skipped")
        self.assertIn("disabled", result["reason"])


if __name__ == "__main__":
    unittest.main()
