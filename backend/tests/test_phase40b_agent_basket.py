"""Phase 40B: one basket interface, and who is allowed to own it.

The risky part is not the storage, it is the identity: deciding that a WhatsApp number
belongs to a signed-in account gives those messages control of that account's cart. Most
of these tests are about when that link may and may not be made.
"""

import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.ai.agents import basket as basket_module
from app.ai.agents.basket import (
    LINKED_BY_NONE,
    LINKED_BY_PHONE,
    LINKED_BY_SESSION,
    MAX_BASKET_LINES,
    MAX_LINE_QUANTITY,
    BasketIdentity,
    BasketLine,
    CartBasket,
    DraftBasket,
    register_identity_resolver,
    resolve_basket,
    resolve_basket_identity,
)
from app.core.config import Settings

TENANT = {"_id": ObjectId(), "name": "Demo Bazaar", "settings": {"currency": "PKR"}}


def item(**overrides):
    base = {
        "_id": ObjectId(),
        "name": "Cotton Shirt",
        "price": 2000,
        "currency": "PKR",
        "isStockTracked": True,
        "stock": {"quantity": 40, "reservedQuantity": 0},
        "variants": [
            {"name": "Blue / Large", "sku": "BL-L", "price": 2200, "isActive": True,
             "stockQuantity": 10, "reservedQuantity": 0, "optionValues": {"Color": "Blue"}},
            {"name": "Red / Small", "sku": "RD-S", "price": 1900, "isActive": True,
             "stockQuantity": 8, "reservedQuantity": 0, "optionValues": {"Color": "Red"}},
        ],
    }
    base.update(overrides)
    return base


class FakeBasket(basket_module._BaseBasket):
    """Exercises the shared behaviour without a database."""

    kind = "fake"

    def __init__(self, tenant=TENANT, identity=None, catalog=None):
        super().__init__(tenant, identity or BasketIdentity(channel="test", tenantId=str(tenant["_id"]), kind="fake"))
        self._lines = []
        self._catalog = {row["_id"]: row for row in (catalog or [])}

    async def _stored_lines(self):
        return list(self._lines)

    async def _write_lines(self, lines):
        self._lines = list(lines)

    async def _item_map(self, lines):
        return {line["itemId"]: self._catalog[line["itemId"]] for line in lines if line.get("itemId") in self._catalog}


class BasketOperationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.shirt = item()
        self.basket = FakeBasket(catalog=[self.shirt])

    async def test_a_new_basket_is_empty(self):
        summary = await self.basket.summary()
        self.assertTrue(summary["isEmpty"])
        self.assertEqual(summary["lineCount"], 0)
        self.assertEqual(summary["subtotal"], 0)

    async def test_adding_an_item_prices_it_from_the_variant(self):
        line = await self.basket.add(self.shirt, 2, variant_index=1)
        self.assertEqual(line.selectedVariantName, "Red / Small")
        self.assertEqual(line.unitPrice, 1900)
        self.assertEqual(line.subtotal, 3800)

    async def test_adding_the_same_variant_twice_accumulates(self):
        """The whole point of the change: a second 'add' must not replace the first."""
        await self.basket.add(self.shirt, 2, variant_index=1)
        await self.basket.add(self.shirt, 3, variant_index=1)
        summary = await self.basket.summary()
        self.assertEqual(summary["lineCount"], 1)
        self.assertEqual(summary["itemCount"], 5)

    async def test_two_variants_are_two_lines(self):
        await self.basket.add(self.shirt, 1, variant_index=0)
        await self.basket.add(self.shirt, 1, variant_index=1)
        summary = await self.basket.summary()
        self.assertEqual(summary["lineCount"], 2)
        self.assertEqual(summary["subtotal"], 4100)

    async def test_quantity_can_be_changed_on_one_line(self):
        first = await self.basket.add(self.shirt, 1, variant_index=0)
        await self.basket.add(self.shirt, 1, variant_index=1)
        updated = await self.basket.set_quantity(first.lineId, 4)
        self.assertEqual(updated.quantity, 4)
        summary = await self.basket.summary()
        self.assertEqual(summary["lineCount"], 2)
        self.assertEqual(summary["itemCount"], 5)

    async def test_removing_one_line_leaves_the_others(self):
        blue = await self.basket.add(self.shirt, 1, variant_index=0)
        await self.basket.add(self.shirt, 1, variant_index=1)
        removed = await self.basket.remove(blue.lineId)
        self.assertEqual(removed.selectedVariantName, "Blue / Large")
        summary = await self.basket.summary()
        self.assertEqual(summary["lineCount"], 1)
        self.assertEqual(summary["lines"][0]["selectedVariantName"], "Red / Small")

    async def test_acting_on_an_unknown_line_returns_none_rather_than_raising(self):
        self.assertIsNone(await self.basket.set_quantity("nope", 2))
        self.assertIsNone(await self.basket.remove("nope"))

    async def test_clear_empties_the_basket_and_reports_what_it_removed(self):
        await self.basket.add(self.shirt, 1, variant_index=0)
        await self.basket.add(self.shirt, 1, variant_index=1)
        self.assertEqual(await self.basket.clear(), 2)
        self.assertTrue((await self.basket.summary())["isEmpty"])

    async def test_quantity_is_clamped_to_the_allowed_range(self):
        line = await self.basket.add(self.shirt, 500, variant_index=0)
        self.assertEqual(line.quantity, MAX_LINE_QUANTITY)
        updated = await self.basket.set_quantity(line.lineId, 0)
        self.assertEqual(updated.quantity, 1)

    async def test_accumulating_past_the_cap_still_stops_at_the_cap(self):
        await self.basket.add(self.shirt, 90, variant_index=0)
        line = await self.basket.add(self.shirt, 50, variant_index=0)
        self.assertEqual(line.quantity, MAX_LINE_QUANTITY)

    async def test_a_basket_cannot_grow_without_limit(self):
        catalog = [item(_id=ObjectId(), name=f"Item {index}", variants=[]) for index in range(MAX_BASKET_LINES + 2)]
        basket = FakeBasket(catalog=catalog)
        for row in catalog[:MAX_BASKET_LINES]:
            await basket.add(row, 1)
        with self.assertRaises(ValueError):
            await basket.add(catalog[MAX_BASKET_LINES], 1)

    async def test_a_line_whose_item_vanished_does_not_break_the_summary(self):
        line = await self.basket.add(self.shirt, 2, variant_index=0)
        self.basket._catalog.clear()
        summary = await self.basket.summary()
        self.assertEqual(summary["lines"][0]["name"], "Unavailable")
        self.assertEqual(summary["lines"][0]["lineId"], line.lineId)


class IdentityResolutionTests(unittest.IsolatedAsyncioTestCase):
    """Who owns the basket, and how confident are we."""

    async def test_a_signed_in_customer_uses_their_own_cart(self):
        user_id = ObjectId()
        identity = await resolve_basket_identity(
            TENANT, channel="customer_portal", customer_user={"_id": user_id, "phone": "03001234567"},
            conversation_id=ObjectId(),
        )
        self.assertEqual(identity.kind, "cart")
        self.assertEqual(identity.linkedBy, LINKED_BY_SESSION)
        self.assertEqual(identity.customerUserId, str(user_id))

    async def test_a_session_beats_a_phone(self):
        """A token is proof; a phone number is an inference. The token must win."""
        signed_in = ObjectId()
        other = {"_id": ObjectId(), "phone": "03009999999", "isPhoneVerified": True}
        users = AsyncMock()
        users.find_one.return_value = other
        with patch.object(basket_module, "get_database", return_value=type("DB", (), {"users": users})()):
            identity = await resolve_basket_identity(
                TENANT, channel="whatsapp",
                customer_user={"_id": signed_in, "phone": "03009999999"},
                conversation_id=ObjectId(), phone="03009999999",
            )
        self.assertEqual(identity.customerUserId, str(signed_in))
        self.assertEqual(identity.linkedBy, LINKED_BY_SESSION)
        users.find_one.assert_not_awaited()

    async def test_a_verified_phone_links_whatsapp_to_the_account_cart(self):
        account_id = ObjectId()
        users = AsyncMock()
        users.find_one.return_value = {"_id": account_id, "phone": "03001234567", "isPhoneVerified": True}
        with patch.object(basket_module, "get_database", return_value=type("DB", (), {"users": users})()):
            identity = await resolve_basket_identity(
                TENANT, channel="whatsapp", conversation_id=ObjectId(), phone="03001234567",
            )
        self.assertEqual(identity.kind, "cart")
        self.assertEqual(identity.linkedBy, LINKED_BY_PHONE)
        self.assertEqual(identity.customerUserId, str(account_id))

    async def test_the_phone_lookup_requires_a_verified_number_by_default(self):
        """An account can claim any number. Only a verified one may be linked."""
        users = AsyncMock()
        users.find_one.return_value = None
        with patch.object(basket_module, "get_database", return_value=type("DB", (), {"users": users})()):
            await resolve_basket_identity(TENANT, channel="whatsapp", conversation_id=ObjectId(), phone="03001234567")
        query = users.find_one.await_args.args[0]
        self.assertTrue(query["isPhoneVerified"])
        self.assertEqual(query["accountType"], "customer")
        self.assertEqual(query["status"], "active")

    async def test_an_operator_can_relax_the_verification_requirement(self):
        relaxed = Settings(jwt_secret_key="x" * 48, whatsapp_cart_link_requires_verified_phone=False)
        users = AsyncMock()
        users.find_one.return_value = None
        with patch.object(basket_module, "settings", relaxed), patch.object(
            basket_module, "get_database", return_value=type("DB", (), {"users": users})()
        ):
            await resolve_basket_identity(TENANT, channel="whatsapp", conversation_id=ObjectId(), phone="03001234567")
        self.assertNotIn("isPhoneVerified", users.find_one.await_args.args[0])

    async def test_a_whatsapp_only_customer_still_gets_a_basket(self):
        """No account is not an error: they must be able to order anyway."""
        users = AsyncMock()
        users.find_one.return_value = None
        conversation_id = ObjectId()
        with patch.object(basket_module, "get_database", return_value=type("DB", (), {"users": users})()):
            identity = await resolve_basket_identity(
                TENANT, channel="whatsapp", conversation_id=conversation_id, phone="03001234567",
            )
        self.assertEqual(identity.kind, "draft")
        self.assertEqual(identity.linkedBy, LINKED_BY_NONE)
        self.assertEqual(identity.conversationId, str(conversation_id))

    async def test_an_anonymous_website_visitor_gets_a_draft_basket(self):
        identity = await resolve_basket_identity(TENANT, channel="website", conversation_id=ObjectId())
        self.assertEqual(identity.kind, "draft")
        self.assertEqual(identity.linkedBy, LINKED_BY_NONE)

    async def test_a_malformed_phone_does_not_link(self):
        users = AsyncMock()
        with patch.object(basket_module, "get_database", return_value=type("DB", (), {"users": users})()):
            identity = await resolve_basket_identity(
                TENANT, channel="whatsapp", conversation_id=ObjectId(), phone="not-a-number",
            )
        self.assertEqual(identity.kind, "draft")
        users.find_one.assert_not_awaited()

    async def test_with_no_account_and_no_conversation_there_is_no_basket(self):
        self.assertIsNone(await resolve_basket_identity(TENANT, channel="owner_preview"))
        self.assertIsNone(await resolve_basket(TENANT, channel="owner_preview"))

    async def test_resolve_basket_returns_the_matching_backend(self):
        cart = await resolve_basket(
            TENANT, channel="customer_portal", customer_user={"_id": ObjectId()}, conversation_id=ObjectId()
        )
        self.assertIsInstance(cart, CartBasket)
        draft = await resolve_basket(TENANT, channel="website", conversation_id=ObjectId())
        self.assertIsInstance(draft, DraftBasket)


class ResolverExtensibilityTests(unittest.IsolatedAsyncioTestCase):
    """The seam that a magic-link flow would use."""

    async def test_a_new_resolver_can_be_registered_ahead_of_the_phone(self):
        original = list(basket_module.IDENTITY_RESOLVERS)
        magic_user = ObjectId()

        async def magic_link_resolver(tenant, context):
            if not context.get("magic_token"):
                return None
            return BasketIdentity(
                channel=context["channel"], tenantId=str(tenant["_id"]), kind="cart",
                customerUserId=str(magic_user), linkedBy="magic_link",
            )

        try:
            register_identity_resolver(magic_link_resolver, before=basket_module._resolve_from_phone)
            self.assertLess(
                basket_module.IDENTITY_RESOLVERS.index(magic_link_resolver),
                basket_module.IDENTITY_RESOLVERS.index(basket_module._resolve_from_phone),
            )
            context_identity = await magic_link_resolver(TENANT, {"channel": "whatsapp", "magic_token": "abc"})
            self.assertEqual(context_identity.linkedBy, "magic_link")
        finally:
            basket_module.IDENTITY_RESOLVERS[:] = original

    async def test_the_anonymous_resolver_stays_last(self):
        """It always answers, so anything after it would never run."""
        self.assertIs(basket_module.IDENTITY_RESOLVERS[-1], basket_module._resolve_anonymous)


class BasketLineShapeTests(unittest.TestCase):
    def test_a_line_serializes_the_fields_the_order_builder_needs(self):
        line = BasketLine(
            lineId="abc", itemId="def", name="Shirt", quantity=2, unitPrice=1900,
            currency="PKR", subtotal=3800, selectedVariantIndex=1,
            selectedVariantName="Red / Small", selectedOptions={"Color": "Red"}, variantSku="RD-S",
        )
        data = line.public_dict()
        for field in ("selectedVariantIndex", "selectedVariantName", "selectedOptions", "variantSku"):
            self.assertIn(field, data)
        self.assertEqual(data["subtotal"], 3800)

    def test_identity_does_not_expose_internal_ids(self):
        identity = BasketIdentity(
            channel="whatsapp", tenantId="t", kind="cart",
            customerUserId="64b7f0c2e1a4d8b9c0a1b2c3", conversationId="c", phone="03001234567",
            linkedBy=LINKED_BY_PHONE,
        )
        data = identity.public_dict()
        self.assertEqual(data, {"channel": "whatsapp", "kind": "cart", "linkedBy": "phone", "hasAccount": True})
        self.assertNotIn("03001234567", repr(data))


if __name__ == "__main__":
    unittest.main()
