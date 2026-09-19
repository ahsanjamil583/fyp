"""Regression cover for Phase 4 (owner agent) and Phase 5 (abuse limits)."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.core import module_guard
from app.core.rate_limit import (
    DEFAULT_RULE,
    InMemoryWindow,
    RateLimitRule,
    _window_start,
    check_rate_limit,
    resolve_rule,
)
from app.services.owner_agent_service import (
    MAX_OWNER_INTENTS,
    _build_owner_reply,
    _classify_owner_intent,
    detect_owner_intents,
)


class OwnerIntentDetectionTests(unittest.TestCase):
    """A compound question used to lose everything after the first matched keyword."""

    def test_compound_question_returns_both_topics(self):
        intents = detect_owner_intents("how many products do I have and what is my total revenue?")
        self.assertIn("catalog_count", intents)
        self.assertIn("business_summary", intents)

    def test_roman_urdu_compound_question(self):
        intents = detect_owner_intents("kitne products hain aur revenue kya hai")
        self.assertIn("catalog_count", intents)
        self.assertIn("business_summary", intents)

    def test_single_topic_stays_single(self):
        self.assertEqual(detect_owner_intents("what is my total revenue?"), ["business_summary"])
        self.assertEqual(detect_owner_intents("how many products do I have?"), ["catalog_count"])

    def test_bare_stock_still_means_inventory(self):
        self.assertEqual(detect_owner_intents("stock"), ["low_stock"])

    def test_product_count_question_is_not_hijacked_by_stock(self):
        self.assertNotIn("low_stock", detect_owner_intents("how many products do I have?"))

    def test_unknown_question_falls_back_to_summary(self):
        self.assertEqual(detect_owner_intents("hello there"), ["business_summary"])

    def test_topics_are_capped_so_answers_stay_readable(self):
        intents = detect_owner_intents("products revenue orders payments chats promotions stock top selling")
        self.assertLessEqual(len(intents), MAX_OWNER_INTENTS)

    def test_no_duplicate_topics(self):
        intents = detect_owner_intents("low stock and inventory and reorder")
        self.assertEqual(len(intents), len(set(intents)))

    def test_primary_intent_helper_matches_first_detected(self):
        message = "how many products do I have and what is my total revenue?"
        self.assertEqual(_classify_owner_intent(message), detect_owner_intents(message)[0])


class OwnerReplyCompositionTests(unittest.TestCase):
    CONTEXT = {
        "analytics": {
            "summary": {"totalTransactions": 4, "totalOrders": 4, "todayOrders": 1},
            "revenue": {"grossRevenue": 9600, "averageOrderValue": 2400},
            "topItems": [{"name": "Grey Tracksuit", "quantity": 2, "revenue": 9600}],
            "lowStockItems": [],
        },
        "topItems": [{"name": "Grey Tracksuit", "quantity": 2, "revenue": 9600}],
        "lowStockItems": [],
        "catalogItems": [{"name": "Grey Tracksuit", "itemType": "product", "status": "active", "stock": {"quantity": 14}}],
        "activeItemCount": 12,
        "activeProductCount": 12,
    }

    def test_both_sections_appear_for_a_compound_question(self):
        reply = _build_owner_reply({"name": "Style"}, "products and revenue", ["catalog_count", "business_summary"], self.CONTEXT, "english")
        self.assertIn("Catalog", reply)
        self.assertIn("Business summary", reply)
        self.assertIn("9,600", reply, "the revenue half must actually be answered")

    def test_single_topic_answer_has_no_section_heading(self):
        reply = _build_owner_reply({"name": "Style"}, "revenue", ["business_summary"], self.CONTEXT, "english")
        self.assertNotIn("Business summary\n", reply)

    def test_reported_count_matches_the_listed_items(self):
        reply = _build_owner_reply({"name": "Style"}, "how many products", ["catalog_count"], self.CONTEXT, "english")
        listed = sum(1 for line in reply.splitlines() if line.startswith("- "))
        self.assertEqual(listed, len(self.CONTEXT["catalogItems"]))
        self.assertIn("12", reply)

    def test_a_string_intent_is_still_accepted(self):
        self.assertTrue(_build_owner_reply({"name": "Style"}, "revenue", "business_summary", self.CONTEXT, "english"))


class RateLimitRoutingTests(unittest.TestCase):
    """One global budget forced the limiter off; routes now carry their own."""

    def test_anonymous_ai_chat_is_the_strictest(self):
        rule = resolve_rule("POST", "/api/v1/public/businesses/style/chat/messages")
        self.assertEqual(rule.name, "public_ai_chat")
        self.assertLess(rule.max_requests, DEFAULT_RULE.max_requests)

    def test_anonymous_orders_are_limited(self):
        self.assertEqual(resolve_rule("POST", "/api/v1/public/businesses/style/orders").name, "public_order")
        self.assertEqual(resolve_rule("POST", "/api/v1/public/businesses/style/transactions").name, "public_order")

    def test_credential_endpoints_are_limited(self):
        for path in ("/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/otp/request"):
            with self.subTest(path=path):
                self.assertEqual(resolve_rule("POST", path).name, "auth_attempt")

    def test_dashboard_reads_get_the_generous_default(self):
        for path in ("/api/v1/tenants/my", "/api/v1/tenants/x/items", "/api/v1/tenants/x/analytics/summary"):
            with self.subTest(path=path):
                self.assertEqual(resolve_rule("GET", path).name, "default")

    def test_reading_the_public_catalog_is_not_throttled_like_chat(self):
        self.assertEqual(resolve_rule("GET", "/api/v1/public/businesses/style/items").name, "default")

    def test_method_is_part_of_the_match(self):
        self.assertEqual(resolve_rule("GET", "/api/v1/public/businesses/style/chat/messages").name, "default")

    def test_sensitive_rules_use_shared_state(self):
        for path, method in (("/api/v1/public/businesses/s/chat/messages", "POST"), ("/api/v1/auth/login", "POST")):
            with self.subTest(path=path):
                self.assertTrue(resolve_rule(method, path).shared)

    def test_default_rule_stays_in_process(self):
        self.assertFalse(DEFAULT_RULE.shared, "a per-request write to enforce 300/min is a poor trade")

    def test_default_budget_stays_generous_enough_for_a_dashboard(self):
        """One dashboard page fans out into many requests and staff share an office IP.

        Tightening this is what made the limiter unusable before, so the floor is pinned.
        """
        from app.core.rate_limit import DEFAULT_RULE as live_default

        self.assertGreaterEqual(live_default.max_requests, 200)
        self.assertEqual(live_default.window_seconds, 60)

    def test_rate_limiting_is_on_by_default(self):
        from app.core.config import Settings

        self.assertTrue(Settings(_env_file=None).rate_limit_enabled)


class InMemoryWindowTests(unittest.TestCase):
    def test_requests_are_allowed_up_to_the_budget_then_refused(self):
        window = InMemoryWindow()
        results = [window.hit("k", 3, 60)[0] for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False])

    def test_keys_do_not_share_a_budget(self):
        window = InMemoryWindow()
        for _ in range(3):
            window.hit("a", 3, 60)
        self.assertTrue(window.hit("b", 3, 60)[0])

    def test_refusal_reports_a_retry_delay(self):
        window = InMemoryWindow()
        window.hit("k", 1, 60)
        allowed, retry_after = window.hit("k", 1, 60)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)


class SharedWindowTests(unittest.IsolatedAsyncioTestCase):
    def test_window_start_is_aligned_so_workers_agree(self):
        moment = datetime(2026, 8, 1, 12, 0, 37, tzinfo=timezone.utc)
        self.assertEqual(_window_start(60, moment).second, 0)
        self.assertEqual(_window_start(60, moment), _window_start(60, moment + timedelta(seconds=20)))

    async def test_a_database_failure_never_takes_the_api_down(self):
        rule = RateLimitRule(name="probe", max_requests=2, window_seconds=60, shared=True)
        with patch("app.core.rate_limit.hit_shared_window", AsyncMock(side_effect=RuntimeError("mongo down"))):
            allowed, _ = await check_rate_limit(rule, "1.2.3.4")
        self.assertTrue(allowed, "the limiter must degrade to local counting, not fail the request")


class AiBudgetTests(unittest.IsolatedAsyncioTestCase):
    """Monthly plan limits are too coarse to stop one bad day."""

    async def _run(self, cap, used_today):
        db = AsyncMock()
        db.messages.count_documents = AsyncMock(return_value=used_today)
        settings_stub = type("S", (), {"ai_daily_message_cap": cap})
        with patch.object(module_guard, "settings", settings_stub), \
             patch.object(module_guard, "get_database", return_value=db):
            await module_guard.ensure_tenant_ai_budget(ObjectId())

    async def test_requests_below_the_cap_pass(self):
        await self._run(cap=300, used_today=299)

    async def test_reaching_the_cap_returns_429(self):
        with self.assertRaises(HTTPException) as ctx:
            await self._run(cap=300, used_today=300)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("daily AI assistant limit", ctx.exception.detail)

    async def test_a_zero_cap_disables_the_check(self):
        await self._run(cap=0, used_today=10_000)


if __name__ == "__main__":
    unittest.main()


class RateLimiterMemoryTests(unittest.TestCase):
    """The limiter keys on client address, so an unbounded dict grows with every distinct
    caller for the lifetime of the process."""

    def test_empty_buckets_are_eventually_pruned(self):
        from app.core.rate_limit import InMemoryWindow

        window = InMemoryWindow()
        window.PRUNE_EVERY = 10
        for index in range(10):
            window.hit(f"client-{index}", max_requests=5, window_seconds=60)
        # Every bucket still holds a hit, so nothing is prunable yet.
        self.assertEqual(len(window._hits), 10)

        # Expire them all, then keep one client active to trigger the sweep.
        for bucket in window._hits.values():
            bucket.clear()
        for _ in range(10):
            window.hit("active-client", max_requests=5, window_seconds=60)

        self.assertIn("active-client", window._hits)
        self.assertEqual(len(window._hits), 1, "the ten idle clients should have been swept")

    def test_pruning_never_drops_a_live_bucket(self):
        from app.core.rate_limit import InMemoryWindow

        window = InMemoryWindow()
        window.hit("busy", max_requests=5, window_seconds=60)
        window.prune()
        self.assertIn("busy", window._hits)

    def test_the_default_limit_comes_from_settings(self):
        """RATE_LIMIT_REQUESTS_PER_MINUTE existed in settings and was read by nothing."""
        from app.core.config import settings
        from app.core.rate_limit import DEFAULT_RULE

        self.assertEqual(DEFAULT_RULE.max_requests, max(1, int(settings.rate_limit_requests_per_minute or 300)))
