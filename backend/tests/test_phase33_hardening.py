"""Regression cover for the Phase 33 stabilisation work.

Each test pins a defect that reached a running deployment: settings that could not
be parsed, a catalog the model never received, a webhook that accepted forged
payloads, and diagnostic routes that published secrets.
"""

import unittest
from unittest.mock import patch

from app.ai.agents.tools import (
    BROWSE_INTENTS,
    MAX_RANKED_ITEMS,
    build_system_prompt,
    classify_message_intent,
    expand_family_tokens,
    format_catalog_for_prompt,
    rank_matching_items,
    score_item_match,
    select_catalog_for_prompt,
)
from app.core.config import PUBLIC_JWT_SECRETS, Settings


def _item(name, price=1000.0, **extra):
    base = {
        "_id": name.lower().replace(" ", "-"),
        "name": name,
        "description": "",
        "tags": [],
        "price": price,
        "currency": "PKR",
        "itemType": "product",
        "isSellable": True,
        "isBookable": False,
        "variants": [],
        "customFields": {},
    }
    base.update(extra)
    return base


CATALOG = [
    _item("White Running Sneakers", 4500.0),
    _item("Black Formal Shoes", 5000.0),
    _item("Brown Leather Loafers", 6200.0),
    _item("Beige Block Heels", 3800.0),
    _item("Blue Sports Shoes", 4200.0),
    _item("Kids Red Canvas Shoes", 2200.0),
    _item("Grey Tracksuit", 4800.0),
]


class SettingsParsingTests(unittest.TestCase):
    """CORS_ORIGINS as a comma-separated string used to abort application start."""

    def test_comma_separated_cors_origins_parse(self):
        settings = Settings(_env_file=None, cors_origins="http://a.test, http://b.test")
        self.assertEqual(settings.cors_origins, ["http://a.test", "http://b.test"])

    def test_list_cors_origins_still_accepted(self):
        settings = Settings(_env_file=None, cors_origins=["http://a.test"])
        self.assertEqual(settings.cors_origins, ["http://a.test"])


class JwtSecretPolicyTests(unittest.TestCase):
    """Placeholder signing keys must not survive a production boot."""

    def _production(self, secret):
        return Settings(_env_file=None, app_env="production", debug=False, jwt_secret_key=secret, bcrypt_rounds=12)

    def test_published_placeholders_are_rejected_in_production(self):
        for secret in PUBLIC_JWT_SECRETS:
            with self.subTest(secret=secret), self.assertRaises(ValueError):
                self._production(secret)

    def test_short_secret_is_rejected_in_production(self):
        with self.assertRaises(ValueError):
            self._production("a" * 20)

    def test_strong_secret_is_accepted_in_production(self):
        settings = self._production("x7Kp" * 16)
        self.assertFalse(settings.jwt_secret_is_public)

    def test_placeholder_is_flagged_but_allowed_outside_production(self):
        settings = Settings(_env_file=None, app_env="development", jwt_secret_key="replace_with_a_strong_random_secret")
        self.assertTrue(settings.jwt_secret_is_public)


class CatalogInPromptTests(unittest.TestCase):
    """The model was told to use catalog data that was never supplied."""

    def test_browse_question_matches_nothing_but_still_gets_the_catalog(self):
        message = "what products do you have and what are the prices?"
        matched = rank_matching_items(message, CATALOG)
        profile = classify_message_intent(message, matched)
        self.assertEqual(matched, [], "broad questions are not expected to keyword-match any item")
        self.assertIn(profile["intent"], BROWSE_INTENTS)
        self.assertEqual(len(select_catalog_for_prompt(matched, CATALOG, profile)), len(CATALOG))

    def test_specific_question_narrows_instead_of_dumping_the_catalog(self):
        message = "what is the price of brown leather loafers?"
        matched = rank_matching_items(message, CATALOG)
        profile = classify_message_intent(message, matched)
        selected = select_catalog_for_prompt(matched, CATALOG, profile)
        self.assertEqual([i["name"] for i in selected][:1], ["Brown Leather Loafers"])
        self.assertLess(len(selected), len(CATALOG))

    def test_system_prompt_embeds_names_and_prices(self):
        profile = {"intent": "ask_recommendation"}
        prompt = build_system_prompt(
            {"name": "Style"}, [], {}, profile, "english", {}, catalog_items=CATALOG
        )
        self.assertIn("Brown Leather Loafers", prompt)
        self.assertIn("6,200", prompt)
        self.assertIn("never invent an item", prompt)

    def test_empty_catalog_is_stated_not_omitted(self):
        self.assertIn("No catalog items available", format_catalog_for_prompt([]))


class FamilySynonymTests(unittest.TestCase):
    """'shoes' has to reach loafers and heels without making them interchangeable."""

    def test_family_word_matches_every_member_of_the_family(self):
        matched = rank_matching_items("do you have shoes?", CATALOG)
        names = {i["name"] for i in matched}
        for expected in ("Brown Leather Loafers", "Beige Block Heels", "White Running Sneakers"):
            self.assertIn(expected, names)

    def test_family_word_does_not_match_outside_the_family(self):
        matched = rank_matching_items("do you have shoes?", CATALOG)
        self.assertNotIn("Grey Tracksuit", {i["name"] for i in matched})

    def test_roman_urdu_family_word_matches(self):
        self.assertTrue(rank_matching_items("koi footwear hai?", CATALOG))

    def test_specific_member_still_outranks_its_siblings(self):
        matched = rank_matching_items("do you have sneakers?", CATALOG)
        self.assertEqual(matched[0]["name"], "White Running Sneakers")

    def test_expansion_adds_the_family_label_only(self):
        expanded = expand_family_tokens({"loafers"})
        self.assertIn("shoes", expanded)
        self.assertNotIn("sneakers", expanded, "siblings must not become interchangeable")

    def test_equally_scoring_family_members_are_not_truncated_to_five(self):
        footwear = [i for i in CATALOG if score_item_match("do you have shoes?", i) > 0]
        self.assertGreater(len(footwear), 5, "fixture must exercise the old cap")
        self.assertEqual(len(rank_matching_items("do you have shoes?", CATALOG)), min(len(footwear), MAX_RANKED_ITEMS))


class StripeWebhookSignatureTests(unittest.TestCase):
    """An unverified webhook can mark any order paid."""

    def test_missing_secret_rejects_even_outside_production(self):
        from app.services import payment_service

        with patch.object(payment_service.settings, "stripe_webhook_secret", ""), \
             patch.object(payment_service.settings, "app_env", "development"):
            self.assertFalse(payment_service._verify_stripe_signature(b'{"id":"evt_1"}', "t=1,v1=deadbeef"))

    def test_valid_signature_is_accepted(self):
        import hashlib
        import hmac
        from datetime import datetime, timezone

        from app.services import payment_service

        secret, payload = "whsec_test", b'{"id":"evt_1"}'
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        digest = hmac.new(secret.encode(), b"%s.%s" % (timestamp.encode(), payload), hashlib.sha256).hexdigest()
        with patch.object(payment_service.settings, "stripe_webhook_secret", secret):
            self.assertTrue(payment_service._verify_stripe_signature(payload, f"t={timestamp},v1={digest}"))

    def test_stale_signature_is_rejected(self):
        import hashlib
        import hmac

        from app.services import payment_service

        secret, payload = "whsec_test", b'{"id":"evt_1"}'
        timestamp = "1000000000"  # far outside the tolerance window
        digest = hmac.new(secret.encode(), b"%s.%s" % (timestamp.encode(), payload), hashlib.sha256).hexdigest()
        with patch.object(payment_service.settings, "stripe_webhook_secret", secret):
            self.assertFalse(payment_service._verify_stripe_signature(payload, f"t={timestamp},v1={digest}"))

    def test_tampered_payload_is_rejected(self):
        import hashlib
        import hmac
        from datetime import datetime, timezone

        from app.services import payment_service

        secret = "whsec_test"
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        digest = hmac.new(secret.encode(), b"%s.%s" % (timestamp.encode(), b'{"id":"evt_1"}'), hashlib.sha256).hexdigest()
        with patch.object(payment_service.settings, "stripe_webhook_secret", secret):
            self.assertFalse(payment_service._verify_stripe_signature(b'{"id":"evt_TAMPERED"}', f"t={timestamp},v1={digest}"))


class DiagnosticDisclosureTests(unittest.TestCase):
    """Readiness and demo-account routes published secrets and seeded logins."""

    def test_secrets_are_reported_as_set_without_revealing_characters(self):
        from app.services.system_validation_service import _mask_secret

        self.assertEqual(_mask_secret(""), "not_set")
        masked = _mask_secret("gsk_live_abcdefghijklmnop")
        self.assertEqual(masked, "set")
        self.assertNotIn("gsk", masked)
        self.assertNotIn("mnop", masked)

    def test_demo_credentials_are_withheld_in_production(self):
        from app.services import system_validation_service

        with patch.object(system_validation_service.settings, "app_env", "production"):
            accounts = system_validation_service.build_demo_accounts()
        self.assertFalse(accounts["available"])
        self.assertNotIn("businessOwner", accounts)

    def test_demo_credentials_remain_available_for_local_demos(self):
        from app.services import system_validation_service

        with patch.object(system_validation_service.settings, "app_env", "development"):
            accounts = system_validation_service.build_demo_accounts()
        self.assertIn("businessOwner", accounts)


class DeadPipelineRemovalTests(unittest.TestCase):
    """The chat service kept a stale copy of the agent pipeline that tests pinned."""

    def test_chat_service_no_longer_redefines_agent_internals(self):
        from app.services import ai_chat_service

        for name in (
            "build_draft_order",
            "classify_message_intent",
            "build_system_prompt",
            "score_item_match",
            "rank_matching_items",
            "generate_openai_response",
            "generate_groq_response",
            "generate_rule_based_response",
            "retrieve_sellable_items",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(ai_chat_service, name), f"{name} should live only in app.ai.agents.tools")

    def test_language_detection_has_a_single_implementation(self):
        from app.ai.agents import tools
        from app.services import ai_chat_service

        self.assertIs(ai_chat_service.detect_language_mode, tools.detect_language_mode)


if __name__ == "__main__":
    unittest.main()
