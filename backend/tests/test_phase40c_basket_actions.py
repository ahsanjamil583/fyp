"""Phase 40C: what the agent decides to do to the basket, and what it is allowed to do.

Nothing the planner decides is applied on the turn it is decided: the orchestrator asks
first and applies only what an affirmative answer replays. So these tests are weighted
towards what the agent PROPOSES - an ambiguous reference, an item nobody mentioned, a
destructive verb - and towards the multi-turn conversations that the old one-shot draft
could not handle at all.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId

from app.ai.agents import actions as actions_module
from app.ai.agents.actions import (
    ADD,
    CHECKOUT,
    CLEAR,
    NONE,
    REMOVE,
    UPDATE,
    VIEW,
    BasketAction,
    BasketPlan,
    classify_basket_intent,
    describe_execution,
    execute_basket_actions,
    extract_bare_quantity,
    is_affirmative,
    is_negative,
    plan_basket_actions,
    score_basket_lines,
)
from app.ai.agents.basket import BasketLine

TENANT_ID = ObjectId()


def catalog_item(name="Zinger Burger", variant=None, item_id=None):
    item = {"_id": item_id or ObjectId(), "name": name, "price": 520, "currency": "PKR"}
    if variant:
        item["agentMatchedVariant"] = variant
    return item


def line(name="Zinger Burger", quantity=2, variant="", line_id=None, unit_price=520.0):
    return BasketLine(
        lineId=line_id or ObjectId().binary.hex(),
        itemId=str(ObjectId()),
        name=name,
        quantity=quantity,
        unitPrice=unit_price,
        currency="PKR",
        subtotal=unit_price * quantity,
        selectedVariantName=variant,
    )


class IntentClassificationTests(unittest.TestCase):
    def test_adding_is_recognised_in_english_and_roman_urdu(self):
        items = [catalog_item()]
        for message in ("I want 2 zinger burgers", "2 burger chahiye", "order a zinger burger"):
            self.assertEqual(classify_basket_intent(message, items, []), ADD, message)

    def test_removing_is_recognised(self):
        lines = [line()]
        for message in ("remove the burger", "burger nikal do", "delete zinger burger", "burger hata do"):
            self.assertEqual(classify_basket_intent(message, [], lines), REMOVE, message)

    def test_a_bare_quantity_changes_an_existing_line(self):
        lines = [line()]
        for message in ("make it 3", "change it to 5", "3 kar do"):
            self.assertEqual(classify_basket_intent(message, [], lines), UPDATE, message)

    def test_a_bare_quantity_with_an_empty_basket_is_not_an_update(self):
        self.assertNotEqual(classify_basket_intent("make it 3", [], []), UPDATE)

    def test_viewing_the_cart_is_recognised(self):
        for message in ("show my cart", "cart dikhao", "what is in my basket"):
            self.assertEqual(classify_basket_intent(message, [], [line()]), VIEW, message)

    def test_clearing_is_recognised_and_beats_other_verbs(self):
        lines = [line()]
        for message in ("clear my cart", "empty the cart", "cancel everything", "remove all items"):
            self.assertEqual(classify_basket_intent(message, [], lines), CLEAR, message)

    def test_checkout_is_recognised(self):
        lines = [line()]
        for message in ("place my order", "checkout", "order kar do", "confirm order"):
            self.assertEqual(classify_basket_intent(message, [], lines), CHECKOUT, message)

    def test_wanting_to_order_an_item_is_adding_not_checking_out(self):
        """'order' appears in both vocabularies; the item is what separates them."""
        self.assertEqual(classify_basket_intent("I want to order a zinger burger", [catalog_item()], []), ADD)

    def test_a_question_is_not_a_basket_instruction(self):
        for message in ("what are your opening hours", "how much is a burger", "do you deliver"):
            self.assertEqual(classify_basket_intent(message, [], [line()]), NONE, message)

    def test_an_empty_message_does_nothing(self):
        self.assertEqual(classify_basket_intent("", [], []), NONE)


class AffirmationTests(unittest.TestCase):
    def test_affirmatives_in_both_languages(self):
        for message in ("yes", "haan", "ji", "ok", "confirm"):
            self.assertTrue(is_affirmative(message), message)

    def test_negatives_in_both_languages(self):
        for message in ("no", "nahi", "cancel", "stop"):
            self.assertTrue(is_negative(message), message)

    def test_a_negative_word_defeats_an_affirmative_one(self):
        self.assertFalse(is_affirmative("no thanks"))

    def test_bare_quantities_are_read_including_zero(self):
        self.assertEqual(extract_bare_quantity("make it 3"), 3)
        self.assertEqual(extract_bare_quantity("make it 0"), 0)
        self.assertIsNone(extract_bare_quantity("make it nice"))


class AddPlanningTests(unittest.TestCase):
    def test_adding_produces_one_action_with_the_quantity(self):
        plan = plan_basket_actions("I want 2 zinger burgers", matched_items=[catalog_item()], basket_lines=[])
        self.assertEqual(plan.intent, ADD)
        self.assertEqual(len(plan.actions), 1)
        self.assertEqual(plan.actions[0].verb, "add")
        self.assertEqual(plan.actions[0].quantity, 2)

    def test_a_matched_variant_is_carried_into_the_action(self):
        item = catalog_item(variant={"variantIndex": 1, "name": "Large"})
        plan = plan_basket_actions("2 large zinger burgers", matched_items=[item], basket_lines=[])
        self.assertEqual(plan.actions[0].variantIndex, 1)
        self.assertIn("Large", plan.actions[0].label)

    def test_only_one_item_is_added_from_a_fuzzy_match(self):
        """Guessing at a second item is how a basket gains things nobody asked for."""
        plan = plan_basket_actions(
            "add a burger", matched_items=[catalog_item("Zinger Burger"), catalog_item("Beef Burger")], basket_lines=[]
        )
        self.assertEqual(len(plan.actions), 1)

    def test_a_bare_item_name_is_not_treated_as_an_instruction(self):
        """"zinger burger" on its own could be a price question. Adding it uninvited is
        worse than answering, so it takes a verb or a quantity."""
        plan = plan_basket_actions("zinger burger", matched_items=[catalog_item("Zinger Burger")], basket_lines=[])
        self.assertFalse(plan.has_actions)

    def test_an_explicit_list_adds_each_named_item(self):
        plan = plan_basket_actions(
            "add zinger burger and cold drink",
            matched_items=[catalog_item("Zinger Burger"), catalog_item("Cold Drink")],
            basket_lines=[],
        )
        self.assertEqual(len(plan.actions), 2)

    def test_adding_accumulates_rather_than_replacing(self):
        """The old draft rebuilt itself each turn, so the first item vanished."""
        existing = line("Zinger Burger", quantity=2)
        plan = plan_basket_actions("also add fries", matched_items=[catalog_item("Fries")], basket_lines=[existing])
        self.assertEqual(plan.intent, ADD)
        self.assertEqual(plan.actions[0].verb, "add")
        self.assertNotIn("clear", [action.verb for action in plan.actions])


class RemovePlanningTests(unittest.TestCase):
    def test_a_named_line_is_removed(self):
        fries = line("Fries", quantity=1)
        plan = plan_basket_actions("remove the fries", matched_items=[], basket_lines=[line(), fries])
        self.assertEqual(plan.actions[0].verb, "remove")
        self.assertEqual(plan.actions[0].lineId, fries.lineId)

    def test_with_one_line_an_unnamed_removal_is_unambiguous(self):
        only = line("Zinger Burger")
        plan = plan_basket_actions("remove it", matched_items=[], basket_lines=[only])
        self.assertEqual(plan.actions[0].lineId, only.lineId)

    def test_with_several_lines_an_unnamed_removal_asks(self):
        plan = plan_basket_actions("remove it", matched_items=[], basket_lines=[line("Burger"), line("Fries")])
        self.assertFalse(plan.has_actions)
        self.assertIn("Which item", plan.clarification)

    def test_an_equal_match_asks_rather_than_guessing(self):
        """Two shirts, one blue one red, and the customer said only 'shirt'."""
        blue = line("Cotton Shirt", variant="Blue / Large")
        red = line("Cotton Shirt", variant="Red / Small")
        plan = plan_basket_actions("remove the shirt", matched_items=[], basket_lines=[blue, red])
        self.assertFalse(plan.has_actions)
        self.assertIn("Which one", plan.clarification)

    def test_a_variant_word_resolves_the_ambiguity(self):
        blue = line("Cotton Shirt", variant="Blue / Large")
        red = line("Cotton Shirt", variant="Red / Small")
        plan = plan_basket_actions("remove the red shirt", matched_items=[], basket_lines=[blue, red])
        self.assertEqual(plan.actions[0].lineId, red.lineId)

    def test_removing_from_an_empty_basket_says_so(self):
        plan = plan_basket_actions("remove the fries", matched_items=[], basket_lines=[])
        self.assertFalse(plan.has_actions)
        self.assertIn("nothing", plan.note.lower())


class UpdatePlanningTests(unittest.TestCase):
    def test_a_bare_quantity_updates_the_only_line(self):
        only = line("Zinger Burger", quantity=2)
        plan = plan_basket_actions("make it 3", matched_items=[], basket_lines=[only])
        self.assertEqual(plan.actions[0].verb, "set_quantity")
        self.assertEqual(plan.actions[0].quantity, 3)
        self.assertEqual(plan.actions[0].lineId, only.lineId)

    def test_a_named_line_is_updated_when_several_exist(self):
        burger = line("Zinger Burger", quantity=2)
        fries = line("Fries", quantity=1)
        plan = plan_basket_actions("change the fries to 4", matched_items=[], basket_lines=[burger, fries])
        self.assertEqual(plan.actions[0].lineId, fries.lineId)
        self.assertEqual(plan.actions[0].quantity, 4)

    def test_an_ambiguous_update_asks(self):
        plan = plan_basket_actions("make it 3", matched_items=[], basket_lines=[line("Burger"), line("Fries")])
        self.assertFalse(plan.has_actions)
        self.assertTrue(plan.clarification)

    def test_setting_a_quantity_to_zero_removes_the_line(self):
        only = line("Zinger Burger", quantity=2)
        plan = plan_basket_actions("make it 0", matched_items=[], basket_lines=[only])
        self.assertEqual(plan.actions[0].verb, "remove")

    def test_an_update_with_no_number_asks_how_many(self):
        only = line("Zinger Burger", quantity=2)
        plan = plan_basket_actions("change the zinger burger", matched_items=[], basket_lines=[only])
        self.assertFalse(plan.has_actions)
        self.assertIn("How many", plan.clarification)


class _RecordingBasket:
    """Counts what actually reached the basket. Nothing more is needed here."""

    tenantId = TENANT_ID

    def __init__(self):
        self.cleared = 0

    async def clear(self):
        self.cleared += 1
        return 2


class ClearPlanningTests(unittest.TestCase):
    """Clearing is destructive, so it is never applied on the first ask."""

    def test_the_first_ask_only_requests_confirmation(self):
        plan = plan_basket_actions("clear my cart", matched_items=[], basket_lines=[line(), line("Fries")])
        self.assertTrue(plan.requiresConfirmation)
        self.assertIn("Are you sure", plan.confirmationPrompt)
        self.assertIn("2", plan.confirmationPrompt)
        # The action the question is about travels with the question, so that agreeing
        # replays what was described rather than re-reading the word "yes" against a cart
        # that may have changed. What matters is that it cannot be applied yet, which is
        # asserted below against the executor rather than inferred from an empty list.
        self.assertEqual([action.verb for action in plan.actions], ["clear"])

    def test_the_first_ask_cannot_reach_the_basket(self):
        plan = plan_basket_actions("clear my cart", matched_items=[], basket_lines=[line(), line("Fries")])
        basket = _RecordingBasket()
        result = asyncio.run(execute_basket_actions(basket, plan, tenant_id=TENANT_ID))
        self.assertEqual(result.blocked, "awaiting_confirmation")
        self.assertEqual(result.applied, [])
        self.assertEqual(basket.cleared, 0)

    def test_the_same_plan_applies_once_it_is_confirmed(self):
        plan = plan_basket_actions("clear my cart", matched_items=[], basket_lines=[line(), line("Fries")])
        basket = _RecordingBasket()
        result = asyncio.run(execute_basket_actions(basket, plan, tenant_id=TENANT_ID, confirmed=True))
        self.assertEqual(result.blocked, "")
        self.assertEqual([row["verb"] for row in result.applied], ["clear"])
        self.assertEqual(basket.cleared, 1)

    def test_a_yes_to_a_pending_clear_clears(self):
        plan = plan_basket_actions(
            "yes", matched_items=[], basket_lines=[line()], pending_confirmation={"verb": "clear"}
        )
        self.assertTrue(plan.has_actions)
        self.assertEqual(plan.actions[0].verb, "clear")
        self.assertFalse(plan.requiresConfirmation)

    def test_a_no_to_a_pending_clear_leaves_the_basket_alone(self):
        plan = plan_basket_actions(
            "no", matched_items=[], basket_lines=[line()], pending_confirmation={"verb": "clear"}
        )
        self.assertFalse(plan.has_actions)
        self.assertIn("Left your cart", plan.note)

    def test_an_unclear_answer_asks_again_rather_than_clearing(self):
        plan = plan_basket_actions(
            "maybe later", matched_items=[], basket_lines=[line()], pending_confirmation={"verb": "clear"}
        )
        self.assertFalse(plan.has_actions)
        self.assertTrue(plan.requiresConfirmation)

    def test_clearing_an_empty_basket_needs_no_confirmation(self):
        plan = plan_basket_actions("clear my cart", matched_items=[], basket_lines=[])
        self.assertFalse(plan.requiresConfirmation)
        self.assertIn("already empty", plan.note)


class CheckoutPlanningTests(unittest.TestCase):
    def test_checkout_makes_no_basket_changes(self):
        """The agent hands over; it never places the order itself."""
        plan = plan_basket_actions("place my order", matched_items=[], basket_lines=[line()])
        self.assertEqual(plan.intent, CHECKOUT)
        self.assertFalse(plan.has_actions)

    def test_checking_out_an_empty_basket_says_so(self):
        plan = plan_basket_actions("place my order", matched_items=[], basket_lines=[])
        self.assertIn("empty", plan.note.lower())


class LineMatchingTests(unittest.TestCase):
    def test_scores_rank_the_better_match_first(self):
        blue = line("Cotton Shirt", variant="Blue / Large")
        red = line("Cotton Shirt", variant="Red / Small")
        scored = score_basket_lines("remove the red shirt", [blue, red])
        self.assertIs(scored[0][1], red)
        self.assertGreater(scored[0][0], scored[1][0])

    def test_an_unmentioned_line_does_not_score(self):
        self.assertEqual(score_basket_lines("remove the pizza", [line("Zinger Burger")]), [])


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.basket = AsyncMock()

    async def test_a_plan_awaiting_confirmation_changes_nothing(self):
        plan = BasketPlan(intent=CLEAR, requiresConfirmation=True, confirmationPrompt="Sure?")
        result = await execute_basket_actions(self.basket, plan, tenant_id=TENANT_ID)
        self.assertEqual(result.blocked, "awaiting_confirmation")
        self.assertFalse(result.changed)
        self.basket.clear.assert_not_awaited()

    async def test_a_confirmed_clear_clears(self):
        self.basket.clear.return_value = 3
        plan = BasketPlan(intent=CLEAR, actions=[BasketAction(verb="clear", label="Cleared")])
        result = await execute_basket_actions(self.basket, plan, tenant_id=TENANT_ID, confirmed=True)
        self.basket.clear.assert_awaited_once()
        self.assertEqual(result.applied[0]["quantity"], 3)

    async def test_an_item_nobody_mentioned_is_refused(self):
        """The guard that keeps a planner bug from becoming a wrong write."""
        plan = BasketPlan(intent=ADD, actions=[BasketAction(verb="add", itemId=str(ObjectId()), quantity=1)])
        result = await execute_basket_actions(
            self.basket, plan, tenant_id=TENANT_ID, allowed_item_ids={str(ObjectId())}
        )
        self.assertFalse(result.changed)
        self.assertIn("could not find", result.rejected[0]["reason"])
        self.basket.add.assert_not_awaited()

    async def test_an_allowed_item_is_added_after_a_live_catalog_check(self):
        item_id = ObjectId()
        items = AsyncMock()
        items.find_one.return_value = {"_id": item_id, "name": "Zinger Burger", "price": 520}
        self.basket.add.return_value = BasketLine(
            lineId="l1", itemId=str(item_id), name="Zinger Burger", quantity=2,
            unitPrice=520, currency="PKR", subtotal=1040,
        )
        plan = BasketPlan(intent=ADD, actions=[BasketAction(verb="add", itemId=str(item_id), quantity=2, label="Added 2")])
        with patch("app.db.mongodb.get_database", return_value=type("DB", (), {"items": items})()):
            result = await execute_basket_actions(
                self.basket, plan, tenant_id=TENANT_ID, allowed_item_ids={str(item_id)}
            )
        query = items.find_one.await_args.args[0]
        self.assertEqual(query["tenantId"], TENANT_ID)
        self.assertEqual(query["status"], "active")
        self.assertTrue(result.changed)

    async def test_an_archived_item_is_refused_even_if_it_was_matched(self):
        item_id = ObjectId()
        items = AsyncMock()
        items.find_one.return_value = None
        plan = BasketPlan(intent=ADD, actions=[BasketAction(verb="add", itemId=str(item_id), quantity=1)])
        with patch("app.db.mongodb.get_database", return_value=type("DB", (), {"items": items})()):
            result = await execute_basket_actions(
                self.basket, plan, tenant_id=TENANT_ID, allowed_item_ids={str(item_id)}
            )
        self.assertFalse(result.changed)
        self.assertIn("not available", result.rejected[0]["reason"])

    async def test_removing_a_line_that_vanished_is_reported_not_raised(self):
        self.basket.remove.return_value = None
        plan = BasketPlan(intent=REMOVE, actions=[BasketAction(verb="remove", lineId="gone")])
        result = await execute_basket_actions(self.basket, plan, tenant_id=TENANT_ID)
        self.assertFalse(result.changed)
        self.assertIn("no longer", result.rejected[0]["reason"])

    async def test_a_full_basket_is_reported_not_raised(self):
        self.basket.add.side_effect = ValueError("A basket can hold at most 40 different lines.")
        item_id = ObjectId()
        items = AsyncMock()
        items.find_one.return_value = {"_id": item_id, "name": "Item", "price": 10}
        plan = BasketPlan(intent=ADD, actions=[BasketAction(verb="add", itemId=str(item_id), quantity=1)])
        with patch("app.db.mongodb.get_database", return_value=type("DB", (), {"items": items})()):
            result = await execute_basket_actions(
                self.basket, plan, tenant_id=TENANT_ID, allowed_item_ids={str(item_id)}
            )
        self.assertIn("at most 40", result.rejected[0]["reason"])

    async def test_one_failing_action_does_not_stop_the_others(self):
        good_id, bad_id = ObjectId(), ObjectId()
        items = AsyncMock()
        items.find_one.side_effect = [None, {"_id": good_id, "name": "Good", "price": 10}]
        self.basket.add.return_value = BasketLine(
            lineId="l", itemId=str(good_id), name="Good", quantity=1,
            unitPrice=10, currency="PKR", subtotal=10,
        )
        plan = BasketPlan(intent=ADD, actions=[
            BasketAction(verb="add", itemId=str(bad_id), quantity=1),
            BasketAction(verb="add", itemId=str(good_id), quantity=1, label="Added Good"),
        ])
        with patch("app.db.mongodb.get_database", return_value=type("DB", (), {"items": items})()):
            result = await execute_basket_actions(
                self.basket, plan, tenant_id=TENANT_ID, allowed_item_ids={str(good_id), str(bad_id)}
            )
        self.assertEqual(len(result.applied), 1)
        self.assertEqual(len(result.rejected), 1)

    async def test_nothing_happens_for_a_plan_with_no_actions(self):
        result = await execute_basket_actions(self.basket, BasketPlan(intent=VIEW), tenant_id=TENANT_ID)
        self.assertFalse(result.changed)
        self.assertFalse(result.rejected)


class DescriptionTests(unittest.TestCase):
    def test_a_blocked_plan_describes_the_question(self):
        plan = BasketPlan(intent=CLEAR, requiresConfirmation=True, confirmationPrompt="Are you sure?")
        result = actions_module.ExecutionResult(blocked="awaiting_confirmation")
        self.assertEqual(describe_execution(result, plan), "Are you sure?")

    def test_applied_actions_are_described(self):
        result = actions_module.ExecutionResult(applied=[{"verb": "add", "label": "Added 2 x Burger"}])
        self.assertIn("Added 2 x Burger", describe_execution(result, BasketPlan(intent=ADD)))


class MultiTurnTests(unittest.TestCase):
    """The conversation the old one-shot draft could not hold."""

    def test_four_turns_end_with_the_right_intentions(self):
        burger = line("Zinger Burger", quantity=2)

        first = plan_basket_actions("2 zinger burgers", matched_items=[catalog_item("Zinger Burger")], basket_lines=[])
        self.assertEqual(first.actions[0].verb, "add")
        self.assertEqual(first.actions[0].quantity, 2)

        second = plan_basket_actions("also add fries", matched_items=[catalog_item("Fries")], basket_lines=[burger])
        self.assertEqual(second.actions[0].verb, "add")

        fries = line("Fries", quantity=1)
        third = plan_basket_actions("make the burgers 3", matched_items=[], basket_lines=[burger, fries])
        self.assertEqual(third.actions[0].verb, "set_quantity")
        self.assertEqual(third.actions[0].quantity, 3)
        self.assertEqual(third.actions[0].lineId, burger.lineId)

        fourth = plan_basket_actions("remove the fries", matched_items=[], basket_lines=[burger, fries])
        self.assertEqual(fourth.actions[0].verb, "remove")
        self.assertEqual(fourth.actions[0].lineId, fries.lineId)


if __name__ == "__main__":
    unittest.main()


class QuestionsNeverWriteToTheCartTests(unittest.TestCase):
    """The basket step writes to a signed-in customer's real cart.

    A question that happens to name an item, or to contain a number, must never add
    anything. "more", "get" and "take" all appear in ordinary questions, and a bare
    number is as often a budget as a quantity.
    """

    def test_asking_about_an_item_does_not_add_it(self):
        items = [catalog_item()]
        for message in (
            "tell me more about the zinger burger",
            "where can I get the zinger burger",
            "do you also have a zinger burger",
            "what is the price of a zinger burger",
            "is the zinger burger available",
        ):
            self.assertEqual(classify_basket_intent(message, items, []), NONE, message)

    def test_a_budget_question_is_not_a_quantity(self):
        self.assertEqual(classify_basket_intent("is the zinger burger under 500?", [catalog_item()], []), NONE)

    def test_a_question_mark_alone_is_enough_to_hold_back(self):
        self.assertEqual(classify_basket_intent("2 zinger burgers?", [catalog_item()], []), NONE)

    def test_a_genuine_instruction_still_adds(self):
        """The guard must not make the agent useless: explicit intent still works."""
        items = [catalog_item()]
        for message in (
            "add a zinger burger",
            "I want 2 zinger burgers",
            "2 zinger burger chahiye",
            "order a zinger burger",
            "2 zinger burgers",
        ):
            self.assertEqual(classify_basket_intent(message, items, []), ADD, message)


class CheckoutDetailsAreNotHarvestedFromQuestionsTests(unittest.TestCase):
    """Checkout details are merged into the stored draft on every turn.

    Picking them out of a question meant "do you accept cash?" set the payment method
    to cash on delivery, and readiness then reported the order ready to place.
    """

    def test_a_payment_question_does_not_choose_a_payment_method(self):
        from app.ai.agents.actions import extract_checkout_details

        for message in ("do you accept cash?", "what payment methods do you take", "is bank transfer available"):
            self.assertEqual(extract_checkout_details(message), {}, message)

    def test_a_delivery_question_does_not_choose_a_fulfillment_type(self):
        from app.ai.agents.actions import extract_checkout_details

        self.assertEqual(extract_checkout_details("do you deliver?"), {})

    def test_substrings_no_longer_match(self):
        """"home" inside "homemade", "self" inside "yourself", "collect" inside
        "collection" all used to set a fulfillment type."""
        from app.ai.agents.actions import extract_checkout_details

        for message in ("i love your homemade sauce", "did you make it yourself", "nice collection"):
            self.assertNotIn("fulfillmentType", extract_checkout_details(message), message)

    def test_a_genuine_instruction_is_still_picked_up(self):
        from app.ai.agents.actions import extract_checkout_details

        self.assertEqual(extract_checkout_details("deliver it and i will pay cash on delivery"),
                         {"fulfillmentType": "delivery", "paymentMethod": "cod"})
        self.assertEqual(extract_checkout_details("i will pick up myself")["fulfillmentType"], "pickup")


class QuestionsNeverChangeTheCartTests(unittest.TestCase):
    """The earlier fix gated only the ADD branch, so REMOVE, CLEAR and CHECKOUT were
    still reachable from a question. Removing a line is unconfirmed and unrecoverable,
    which makes it the worst of the three."""

    def test_asking_how_to_remove_does_not_remove(self):
        for message in (
            "how do i remove items from my cart?",
            "what does cancel mean?",
            "is it possible to delete an item?",
            "can you tell me how to clear my cart?",
        ):
            self.assertEqual(classify_basket_intent(message, [], [line()]), NONE, message)

    def test_asking_about_checkout_does_not_check_out(self):
        self.assertEqual(classify_basket_intent("how do i place an order?", [], [line()]), NONE)

    def test_reading_the_cart_is_still_allowed(self):
        """Viewing is read-only, so a question that asks what is in the cart is answered
        rather than refused."""
        for message in ("what is in my basket", "show my cart", "cart dikhao"):
            self.assertEqual(classify_basket_intent(message, [], [line()]), VIEW, message)

    def test_a_named_destructive_instruction_still_works(self):
        for message in ("remove the zinger burger", "please remove the burger", "can you remove the zinger burger"):
            self.assertEqual(classify_basket_intent(message, [], [line()]), REMOVE, message)
        self.assertEqual(classify_basket_intent("clear my cart", [], [line()]), CLEAR)


class PoliteOrdersStillWorkTests(unittest.TestCase):
    """English asks for things by pretending to ask a question. Treating every
    interrogative as an enquiry turned the most common polite phrasing into a no-op."""

    def test_polite_interrogative_orders_add_to_the_cart(self):
        items = [catalog_item()]
        for message in (
            "can I get 2 zinger burgers?",
            "could i have 2 zinger burgers please",
            "may i have a zinger burger",
            "can you add 2 zinger burgers",
            "I'd like 2 zinger burgers",
        ):
            self.assertEqual(classify_basket_intent(message, items, []), ADD, message)

    def test_an_informational_opener_still_wins(self):
        """"where can I get the burger" contains "can i get" but is not an order."""
        items = [catalog_item()]
        for message in (
            "where can I get the zinger burger",
            "how can i order a zinger burger",
            "what can i get for 500",
        ):
            self.assertEqual(classify_basket_intent(message, items, []), NONE, message)


class DestructiveVerbsNeverActOnAQuestionTests(unittest.TestCase):
    """The first attempt at this gate let a polite shape bypass it for ANY verb, so
    "can I remove an item later?" deleted a line. Deleting somebody's cart line unasked
    is not something they can undo, so destructive verbs get no polite bypass at all."""

    def test_capability_and_policy_questions_do_nothing(self):
        for message in (
            "can I remove an item later?",
            "can i delete a line from my cart?",
            "could you remove items automatically?",
            "may I cancel an order after placing it?",
            "can i clear my cart later",
            "is checkout free",
            "cancel policy",
        ):
            self.assertEqual(classify_basket_intent(message, [], [line()]), NONE, message)

    def test_a_refusal_is_not_an_instruction(self):
        """"no, don't remove it" names the verb but asks for the opposite."""
        for message in ("no dont remove it", "dont clear my cart", "nahi hatao"):
            self.assertEqual(classify_basket_intent(message, [], [line()]), NONE, message)

    def test_cancel_everything_is_still_a_clear(self):
        """"cancel" is in both the destructive and the negative vocabularies, so a naive
        refusal check made this phrase mean its own opposite."""
        self.assertEqual(classify_basket_intent("cancel everything", [], [line()]), CLEAR)

    def test_direct_destructive_instructions_still_work(self):
        for message in ("remove the zinger burger", "please remove the burger", "burger nikal do"):
            self.assertEqual(classify_basket_intent(message, [], [line()]), REMOVE, message)


class OrderingPhrasingCoverageTests(unittest.TestCase):
    """The guard against question-shaped adds must not swallow the ordinary ways people
    order, in either language."""

    def test_spelled_quantities_count(self):
        items = [catalog_item()]
        for message in ("one burger please", "i'll take two burgers"):
            self.assertEqual(classify_basket_intent(message, items, []), ADD, message)

    def test_roman_urdu_requests_work(self):
        items = [catalog_item()]
        for message in ("mujhe do burger chahiye", "kya mujhe 2 burger mil sakte hain", "do burger bhejo"):
            self.assertEqual(classify_basket_intent(message, items, []), ADD, message)

    def test_wanting_to_know_is_not_wanting_to_buy(self):
        """"want" is an add hint, so "I want to know the price" re-opened the very bug
        the question gate was added to close."""
        items = [catalog_item()]
        for message in (
            "i want to know the price of the zinger burger",
            "i need to know if you have burgers",
        ):
            self.assertEqual(classify_basket_intent(message, items, []), NONE, message)


class DestructiveActionsConfirmUnlessOrderedTests(unittest.TestCase):
    """Three rounds of adding keywords each closed some holes and opened others.

    The structural rule is what makes this safe: a line is removed without asking ONLY
    when removal was given as a direct order. Every hedge, musing or half-caught
    question gets a confirmation prompt instead, so the keyword lists no longer have to
    be exhaustive to prevent an unrecoverable deletion.
    """

    def _plan(self, message):
        lines = [line(), line(line_id="L2", name="Fries")]
        return plan_basket_actions(message, matched_items=[], basket_lines=lines)

    def test_hedges_and_musings_never_apply_a_removal(self):
        for message in (
            "i was going to remove the fries",
            "maybe i should remove the fries",
            "i might remove the fries",
            "should you remove the fries",
            "we usually remove items before paying",
            "last time i had to remove an item",
            "planning to cancel the order",
        ):
            self.assertEqual(self._plan(message).actions, [], message)

    def test_refusals_never_apply_a_removal(self):
        for message in ("do not remove the fries", "don't remove the fries", "leave it, do not delete"):
            self.assertEqual(self._plan(message).actions, [], message)

    def test_a_direct_order_still_removes_immediately(self):
        """The guard must not turn every removal into a two-step conversation."""
        for message in ("remove the zinger burger", "please remove the fries", "fries nikal do"):
            plan = self._plan(message)
            self.assertEqual([action.verb for action in plan.actions], ["remove"], message)
            self.assertFalse(plan.requiresConfirmation, message)

    def test_a_negated_add_does_not_add(self):
        items = [catalog_item()]
        for message in ("don't add the burger", "no thanks, don't add anything"):
            plan = plan_basket_actions(message, matched_items=items, basket_lines=[])
            self.assertEqual(plan.actions, [], message)

    def test_a_note_alongside_an_order_still_orders(self):
        """"no onions" is a note, not a refusal; only a negation in front of the verb
        counts, or ordinary orders would start failing."""
        items = [catalog_item()]
        self.assertEqual(classify_basket_intent("no onions, add a zinger burger", items, []), ADD)

    def test_past_tense_is_context_not_an_order(self):
        items = [catalog_item()]
        self.assertEqual(classify_basket_intent("i had ordered 2 burgers", items, []), NONE)

    def test_cart_questions_still_show_the_cart(self):
        """"cart" is in both the order and view vocabularies, and treating it as an
        action word made every question about a cart return nothing."""
        for message in ("what is in my cart", "whats in my cart?", "cart dikhao"):
            self.assertEqual(classify_basket_intent(message, [], [line()]), VIEW, message)


class CartWritesSurviveAdversarialPhrasingTests(unittest.TestCase):
    """The fifth attempt at this guard. The four before it each added words to a hint
    list and each left holes, so the rules that decide a DESTRUCTIVE action no longer
    depend on those lists being complete."""

    def _plan(self, message, lines=None, matched=None):
        return plan_basket_actions(message, matched_items=matched or [], basket_lines=lines or [line()])

    def test_a_modifier_orders_the_item_rather_than_deleting_it(self):
        """"without", "less" and "minus" used to be removal verbs, so asking for a burger
        without onions deleted the burger.

        The safety property is that it never deletes. Reading it as an order is the
        sensible remaining choice: nobody says "without onions" about a burger they are
        not asking for."""
        for message in ("burger without onions", "zinger burger minus the cheese",
                        "2 burgers without onions", "add a burger without onions"):
            intent = classify_basket_intent(message, [catalog_item()], [line()])
            self.assertEqual(intent, ADD, message)
            self.assertNotEqual(intent, REMOVE, message)

    def test_an_unrelated_sentence_never_deletes_the_only_line(self):
        """A one-item cart used to be emptied whenever nothing matched, which turned
        every misread into an unrecoverable deletion."""
        for message in ("cancel the meeting", "delete my account", "remove ads",
                        "please cancel my gym membership", "cancel culture is bad"):
            self.assertEqual(self._plan(message).actions, [], message)

    def test_a_removal_that_points_at_the_only_line_still_works(self):
        for message in ("remove it", "hata do"):
            plan = self._plan(message)
            self.assertEqual([action.verb for action in plan.actions], ["remove"], message)

    def test_declining_to_remove_removes_nothing(self):
        for message in ("delete nothing", "cancel nothing", "remove none of it"):
            self.assertEqual(self._plan(message).actions, [], message)

    def test_reported_speech_is_not_an_instruction(self):
        for message in ("she said remove the fries", "quote remove the fries unquote",
                        "remove is a strong word"):
            self.assertEqual(self._plan(message).actions, [], message)

    def test_a_number_in_a_sentence_about_an_item_is_not_a_quantity(self):
        """A price or a fact containing a digit used to order that many."""
        for message in ("burger under 500", "the burger is 500 rupees right",
                        "the burger has 3 patties", "burger 500 ka hai"):
            self.assertEqual(self._plan(message, lines=[], matched=[catalog_item()]).actions, [], message)

    def test_an_article_alone_does_not_order(self):
        for message in ("there was a hair in the burger", "the burger was a disappointment",
                        "i do not like the burger"):
            self.assertEqual(self._plan(message, lines=[], matched=[catalog_item()]).actions, [], message)

    def test_a_stall_does_not_resolve_a_pending_clear(self):
        """"ok but what is the total first" is a question, not agreement."""
        for message in ("okay but what is the total first", "ok wait", "sure, what is in it",
                        "ok, actually just add fries", "confirm my address is 12 mall road"):
            plan = plan_basket_actions(message, matched_items=[], basket_lines=[line()],
                                       pending_confirmation={"verb": "clear"})
            self.assertNotIn("clear", [action.verb for action in plan.actions], message)

    def test_agreeing_to_a_removal_removes_only_that_line(self):
        """Every confirmation used to be labelled "clear", so saying yes to "should I
        remove the fries?" destroyed the whole cart instead of dropping one line."""
        lines = [line(line_id="L1", name="Zinger Burger"), line(line_id="L2", name="Fries")]
        pending = {"verb": REMOVE, "lineId": "L2"}
        plan = plan_basket_actions("yes", matched_items=[], basket_lines=lines, pending_confirmation=pending)

        self.assertEqual([action.verb for action in plan.actions], ["remove"])
        self.assertEqual([action.lineId for action in plan.actions], ["L2"])

    def test_declining_a_pending_removal_removes_nothing(self):
        lines = [line(line_id="L1", name="Zinger Burger"), line(line_id="L2", name="Fries")]
        plan = plan_basket_actions("no", matched_items=[], basket_lines=lines,
                                   pending_confirmation={"verb": REMOVE, "lineId": "L2"})
        self.assertEqual(plan.actions, [])

    def test_a_pending_removal_carries_the_line_it_asked_about(self):
        """Without the id, a "yes" cannot be told from agreement to anything else."""
        lines = [line(line_id="L1", name="Zinger Burger"), line(line_id="L2", name="Fries")]
        plan = plan_basket_actions("i was going to remove something", matched_items=[], basket_lines=lines)
        if plan.requiresConfirmation:
            self.assertTrue(plan.confirmationLineId, "a confirmation must name its target")
        else:
            self.assertEqual(plan.actions, [], "an indirect phrasing must not act unprompted")


class CheckoutDetailsNeedAChoiceTests(unittest.TestCase):
    def test_asking_what_is_accepted_chooses_nothing(self):
        from app.ai.agents.actions import extract_checkout_details

        for message in ("can i get cash on delivery?", "could i get cod?", "can i take pickup?",
                        "can we get home delivery?"):
            self.assertEqual(extract_checkout_details(message), {}, message)

    def test_a_refusal_never_sets_the_thing_refused(self):
        from app.ai.agents.actions import extract_checkout_details

        for message in ("i dont have cash", "i cant pay cash", "no cash please",
                        "dont deliver it, ill pick it up"):
            self.assertEqual(extract_checkout_details(message), {}, message)

    def test_mentioning_a_word_in_passing_chooses_nothing(self):
        from app.ai.agents.actions import extract_checkout_details

        for message in ("the delivery guy was rude", "my bank is closed today",
                        "your delivery is always late", "someone said you take cash"):
            self.assertEqual(extract_checkout_details(message), {}, message)

    def test_a_real_choice_is_still_recorded(self):
        from app.ai.agents.actions import extract_checkout_details

        self.assertEqual(extract_checkout_details("i will pay cash on delivery")["paymentMethod"], "cod")
        self.assertEqual(extract_checkout_details("deliver it to my home")["fulfillmentType"], "delivery")
        self.assertEqual(extract_checkout_details("cash on delivery")["paymentMethod"], "cod")
        self.assertEqual(extract_checkout_details("khud aunga")["fulfillmentType"], "pickup")
