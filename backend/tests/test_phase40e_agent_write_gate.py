"""The one rule that keeps the agent from writing to a cart nobody asked it to change.

Six rounds of this project tried to make the intent classifier reliable enough to be
trusted with a write. Five independent reviews broke every one of them, usually within
minutes, because "is this sentence an instruction?" is not a question a keyword list can
answer. The rules got better each round and were still wrong often enough to lose a
customer's cart.

So the rules no longer decide whether to write. They decide what to PROPOSE, and the
customer decides whether it happens. That is the invariant these tests exist to hold:

    `execute_basket_actions` is reached with a non-empty action list ONLY on the branch
    of `_run_basket_step` that requires an affirmative answer to a question asked on the
    previous turn.

The corpus below is not a list of phrasings that once broke something and were then
patched - that is what the previous six rounds did, and it is why they kept failing.
These sentences are here as evidence for a claim about the structure: that it no longer
matters how badly the classifier misreads them.
"""

import asyncio
import dataclasses
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bson import ObjectId

from app.ai.agents.actions import checkout_readiness, extract_checkout_details
from app.ai.agents.basket import BasketLine
from app.ai.agents.orchestrator_agent import (
    MAX_REASKS,
    PROPOSAL_TTL,
    _basket_reply,
    _run_basket_step,
)

TENANT_ID = ObjectId()
BURGER_ID = str(ObjectId())
FRIES_ID = str(ObjectId())


def catalog_item(name="Zinger Burger", item_id=None):
    return {
        "_id": ObjectId(item_id) if item_id else ObjectId(BURGER_ID),
        "name": name,
        "price": 500.0,
        "currency": "PKR",
        "itemType": "product",
        "isSellable": True,
        "status": "active",
        "tenantId": TENANT_ID,
    }


def line(name="Zinger Burger", line_id="L1", item_id=None, quantity=2):
    return BasketLine(
        lineId=line_id,
        itemId=item_id or BURGER_ID,
        name=name,
        quantity=quantity,
        unitPrice=500.0,
        currency="PKR",
        subtotal=500.0 * quantity,
    )


class RecordingBasket:
    """A basket that records every mutation instead of performing one.

    The assertions below are about `mutations` rather than about the resulting cart,
    because the thing being tested is whether the basket is TOUCHED at all.
    """

    def __init__(self, starting_lines):
        self.tenantId = TENANT_ID
        self._lines = list(starting_lines)
        self.mutations = []

    async def lines(self):
        return list(self._lines)

    async def summary(self):
        return {
            "isEmpty": not self._lines,
            "itemCount": sum(row.quantity for row in self._lines),
            "subtotal": sum(row.subtotal for row in self._lines),
            "currency": "PKR",
            "lines": [row.public_dict() for row in self._lines],
        }

    async def clear(self):
        removed = len(self._lines)
        # Records WHAT was destroyed, not just that something was. Recording the verb
        # alone let "cleared 40 units under a prompt that said 1 item" pass, and let a
        # removal land on a different line than the one the question named.
        self.mutations.append(("clear", [f"{row.name}:{row.quantity}" for row in self._lines]))
        self._lines = []
        return removed

    async def remove(self, line_id):
        for index, row in enumerate(self._lines):
            if row.lineId == line_id:
                self.mutations.append(("remove", row.name))
                return self._lines.pop(index)
        self.mutations.append(("remove", None))
        return None

    async def set_quantity(self, line_id, quantity):
        for index, row in enumerate(self._lines):
            if row.lineId == line_id:
                self.mutations.append(("set_quantity", row.name, quantity))
                self._lines[index] = dataclasses.replace(row, quantity=quantity)
                return self._lines[index]
        self.mutations.append(("set_quantity", None, quantity))
        return None

    async def add(self, item, quantity, variant_index=None):
        self.mutations.append(("add", item["name"], quantity))
        row = line(item["name"], f"L{len(self._lines) + 9}", str(item["_id"]), quantity)
        self._lines.append(row)
        return row


class _FakeItems:
    @staticmethod
    async def find_one(query):
        return catalog_item("Zinger Burger", str(query["_id"]))


class _FakeDB:
    items = _FakeItems


def two_lines():
    return [line("Zinger Burger", "L1"), line("Fries", "L2", FRIES_ID)]


def step(basket, message, matched=None, pending=None):
    return asyncio.run(_run_basket_step(basket, message, matched or [], pending))


# Sentences that must never change a basket on their own. Each group is a class of
# message an earlier round read as an instruction.
NOT_INSTRUCTIONS = [
    # Ordering words used as nouns. All of these are in the ordering vocabulary.
    "my last order was delivered late",
    "the delivery guy was rude",
    "your cart page is broken on mobile",
    "i never got a confirm message",
    "do you take pickup orders",
    "is delivery free",
    "can i book a table for saturday",
    "the order confirm button does nothing",
    # Questions, including the one the text normaliser used to corrupt into "whai".
    "why did you add a burger to my cart",
    "why would i order 5 burgers",
    "what happens if i order two burgers",
    "how much is a zinger burger",
    "kya aap burger deliver karte ho",
    # Reported speech: someone else's instruction, quoted.
    "my friend said i should order the zinger burger",
    "she told me to remove the fries",
    "someone said add 3 burgers",
    # Hypotheticals.
    "if i order 2 burgers will it be cheaper",
    "i was going to remove the fries",
    "suppose i add 10 burgers",
    # Refusals.
    "dont add any burgers",
    "please do not clear my cart",
    # The past tense.
    "i already ordered a burger yesterday",
    "we cleared the cart last time",
]

# (message, the verb it should propose, how many lines the cart needs for it to be
# unambiguous). "make it 3" against a two-line cart names no item, so asking which one
# is the right answer there, not a quantity change.
REAL_INSTRUCTIONS = [
    ("add 2 zinger burgers", "add", 2),
    ("i want a zinger burger", "add", 2),
    ("remove the fries", "remove", 2),
    ("clear my cart", "clear", 2),
    ("make it 3", "set_quantity", 1),
]


def cart(size):
    return two_lines() if size > 1 else [line("Zinger Burger", "L1")]


class NothingWritesWithoutAnAnswerTests(unittest.TestCase):
    """Part one of the invariant: a single message never changes anything."""

    def setUp(self):
        import app.ai.agents.actions as actions_module
        import app.db.mongodb as mongodb_module

        self._patched = []
        for module in (actions_module, mongodb_module):
            self._patched.append((module, getattr(module, "get_database", None)))
            module.get_database = lambda: _FakeDB()

    def tearDown(self):
        for module, original in self._patched:
            if original is not None:
                module.get_database = original

    def test_no_message_however_it_reads_changes_the_cart_on_its_own(self):
        for message in NOT_INSTRUCTIONS:
            for matched in ([], [catalog_item()]):
                with self.subTest(message=message, matched=bool(matched)):
                    basket = RecordingBasket(two_lines())
                    step(basket, message, matched=matched)
                    self.assertEqual(basket.mutations, [], message)

    def test_a_genuine_instruction_does_not_write_on_its_first_utterance_either(self):
        # This is the part that makes the guard structural rather than a better filter:
        # correctly understanding the message still does not earn the right to write.
        for message, _verb, size in REAL_INSTRUCTIONS:
            with self.subTest(message=message):
                basket = RecordingBasket(cart(size))
                step(basket, message, matched=[catalog_item()])
                self.assertEqual(basket.mutations, [], message)

    def test_a_genuine_instruction_is_proposed_back_to_the_customer(self):
        # The agent still has to be useful. A proposal must name what it would do and
        # come back as a question.
        for message, expected_verb, size in REAL_INSTRUCTIONS:
            with self.subTest(message=message):
                basket = RecordingBasket(cart(size))
                _summary, plan, result, pending = step(basket, message, matched=[catalog_item()])
                self.assertEqual(result["blocked"], "awaiting_confirmation", message)
                self.assertTrue(plan["confirmationPrompt"], message)
                self.assertIn(
                    expected_verb,
                    [action["verb"] for action in pending["actions"]],
                    message,
                )


class AnAnswerResolvesTheProposalTests(unittest.TestCase):
    """Part two: yes applies exactly what was described, no applies nothing."""

    def setUp(self):
        import app.ai.agents.actions as actions_module
        import app.db.mongodb as mongodb_module

        self._patched = []
        for module in (actions_module, mongodb_module):
            self._patched.append((module, getattr(module, "get_database", None)))
            module.get_database = lambda: _FakeDB()

    def tearDown(self):
        for module, original in self._patched:
            if original is not None:
                module.get_database = original

    def test_yes_applies_exactly_what_the_question_described(self):
        for message, _verb, size in REAL_INSTRUCTIONS:
            with self.subTest(message=message):
                _s, _p, _r, pending = step(
                    RecordingBasket(cart(size)), message, matched=[catalog_item()]
                )
                described = [action["verb"] for action in pending["actions"]]

                basket = RecordingBasket(cart(size))
                step(basket, "yes", pending=pending)
                self.assertEqual([entry[0] for entry in basket.mutations], described, message)

    def test_no_applies_nothing_and_closes_the_question(self):
        for message, _verb, size in REAL_INSTRUCTIONS:
            with self.subTest(message=message):
                _s, _p, _r, pending = step(
                    RecordingBasket(cart(size)), message, matched=[catalog_item()]
                )
                basket = RecordingBasket(cart(size))
                _s, _p, _r, after = step(basket, "no", pending=pending)
                self.assertEqual(basket.mutations, [], message)
                # The proposal must not survive a refusal, or a later unrelated "ok"
                # would resurrect it.
                self.assertFalse(after.get("actions"), message)

    def test_answering_a_removal_question_does_not_clear_the_cart(self):
        # The regression a previous pass introduced: every pending confirmation was
        # labelled a clear, so agreeing to remove one item emptied the basket.
        #
        # This test used to guard that behind `if pending.get("actions"):`, which was
        # always None, so its only assertion never ran and it passed whatever the code
        # did. The proposal is now built from a message that reliably produces one.
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "remove the fries")
        self.assertEqual([action["verb"] for action in pending["actions"]], ["remove"])

        basket = RecordingBasket(two_lines())
        step(basket, "yes", pending=pending)
        self.assertEqual(basket.mutations, [("remove", "Fries")])

    def test_a_malformed_or_stale_proposal_neither_crashes_nor_writes(self):
        # Stored confirmations are read back from the database and can be older than the
        # running code. A bad row must cost the customer a re-ask, not a 500 mid-order.
        # Each row is given a LIVE lifetime, or `_proposal_is_live` rejects it before the
        # replay branch is reached and the "nor writes" half of this test is free - which
        # it was: deleting every per-action guard left it passing.
        live = {
            "proposedAt": datetime.now(timezone.utc).isoformat(),
            "reasksLeft": 2,
            "cartScope": [],
        }
        # Rows with no usable `actions` reach the replay branch with nothing to replay, so
        # they test only that nothing crashes. They are kept, and the rows that DO carry a
        # replayable action are the ones that make the "nor writes" half mean something.
        for junk in (
            {**live, "actions": [{}]},
            {**live, "actions": [{"verb": ""}]},
            {**live, "actions": "nonsense"},
            {**live, "actions": [None, 7]},
            {**live, "actions": [{"verb": "remove", "lineId": "no-such-line", "subject": "Ghost"}]},
            {**live, "actions": [{"verb": "remove", "subject": "Zinger Burger"}]},
            {**live, "actions": [{"verb": "clear", "quantity": "lots"}]},
            {**live, "actions": [{"verb": "add", "quantity": "lots"}]},
            {**live, "verb": "clear"},
            "not a dict",
        ):
            with self.subTest(junk=junk):
                # "yes", not a question. The old version used a message that could never
                # be affirmative, so the replay branch was never reached and the "nor
                # writes" half of this test was free.
                basket = RecordingBasket([line("Zinger Burger", "L1")])
                step(basket, "yes", pending=junk)
                self.assertEqual(basket.mutations, [])


class AProposalHasAScopeAndALifetimeTests(unittest.TestCase):
    """What the ninth-pass review broke, and how.

    The reviewer could not reach the executor from any branch but the affirmative one -
    the invariant held inside the function. They then pointed out that the invariant is
    written about the CART and was only enforced about the FUNCTION, and broke it from
    outside: the cart page and the other channels write the same document, and the
    proposal had no scope, no lifetime, and no owner.
    """

    def setUp(self):
        import app.ai.agents.actions as actions_module
        import app.db.mongodb as mongodb_module

        self._patched = []
        for module in (actions_module, mongodb_module):
            self._patched.append((module, getattr(module, "get_database", None)))
            module.get_database = lambda: _FakeDB()

    def tearDown(self):
        for module, original in self._patched:
            if original is not None:
                module.get_database = original

    def test_agreeing_to_clear_one_item_does_not_empty_a_cart_that_grew(self):
        # The reviewer's scenario. "clear my cart" against a one-item cart, then the
        # customer adds two more lines from the cart page - the same document, a
        # different surface - and says "ok". A stored `clear` names no lines, so it used
        # to take everything that happened to be there by then.
        _s, _p, _r, pending = step(
            RecordingBasket([line("Zinger Burger", "L1", quantity=1)]), "clear my cart"
        )
        self.assertEqual(pending["cartScope"], [f"L1:{BURGER_ID}:1"])

        grown = RecordingBasket(
            [
                line("Zinger Burger", "L1", quantity=1),
                line("Fries", "L2", FRIES_ID),
                line("Cola", "L3"),
            ]
        )
        _s, plan, result, again = step(grown, "ok", pending=pending)
        self.assertEqual(grown.mutations, [])
        self.assertEqual(result["blocked"], "awaiting_confirmation")
        self.assertIn("changed", plan["confirmationPrompt"])
        # And the re-asked question is scoped to what is actually there now.
        self.assertEqual(
            again["cartScope"],
            sorted([f"L1:{BURGER_ID}:1", f"L2:{FRIES_ID}:2", f"L3:{BURGER_ID}:2"]),
        )
        # The lifetime is inherited AND spent, so a cart that keeps changing cannot renew
        # a destructive proposal for ever. Asserting the budget was unchanged, as this
        # test first did, was asserting the livelock: a re-ask whose cause is permanent -
        # a renamed item, a deleted line - repeated the same unanswerable question for the
        # full timeout.
        self.assertEqual(again["proposedAt"], pending["proposedAt"])
        self.assertEqual(again["reasksLeft"], pending["reasksLeft"] - 1)

    def test_agreeing_to_clear_the_same_cart_still_clears_it(self):
        # The scope check must not make clearing impossible.
        start = [line("Zinger Burger", "L1"), line("Fries", "L2", FRIES_ID)]
        _s, _p, _r, pending = step(RecordingBasket(list(start)), "clear my cart")
        basket = RecordingBasket(list(start))
        step(basket, "yes", pending=pending)
        self.assertEqual([entry[0] for entry in basket.mutations], ["clear"])

    def test_a_proposal_expires_rather_than_waiting_forever_for_an_ok(self):
        # Without a lifetime, a proposal made before a tenant hit its AI budget stayed
        # live indefinitely and the next "ok" - days later, meaning something else -
        # replayed it.
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "clear my cart")
        stale = {
            **pending,
            "proposedAt": (
                datetime.now(timezone.utc) - PROPOSAL_TTL - timedelta(minutes=1)
            ).isoformat(),
        }
        basket = RecordingBasket(two_lines())
        step(basket, "yes", pending=stale)
        self.assertEqual(basket.mutations, [])

    def test_a_proposal_with_no_timestamp_is_not_trusted(self):
        # Rows written by older code. A replay has to be attributable to a question the
        # customer can still remember being asked.
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "clear my cart")
        undated = {key: value for key, value in pending.items() if key != "proposedAt"}
        basket = RecordingBasket(two_lines())
        step(basket, "yes", pending=undated)
        self.assertEqual(basket.mutations, [])

    def test_answering_the_agents_other_question_drops_the_order_but_says_so(self):
        # This test used to assert that the proposal was CARRIED, because dropping it
        # silently lost the customer's order. Carrying it turned out to be the worse half
        # of the trade: three ordinary messages later, an "ok" meaning "ok, thanks"
        # applied it. The answer is to drop it and say so, which is what makes a silent
        # loss impossible instead of bounded.
        _s, _p, _r, pending = step(
            RecordingBasket([]), "i want a zinger burger", matched=[catalog_item()]
        )
        self.assertTrue(pending["actions"])

        basket = RecordingBasket([])
        _s, plan, _r, after = step(basket, "delivery", pending=pending)
        self.assertEqual(basket.mutations, [])
        self.assertEqual(after, {})
        # The sentence is the whole point: the customer is told their order was not placed.
        self.assertIn("not read that as a yes", plan["note"])
        self.assertIn("Zinger Burger", plan["note"])

    def test_a_message_that_is_not_an_answer_never_applies_the_proposal(self):
        # The guard this names is the answer classifier itself. Without this, making it
        # return YES for everything left the whole suite green - found by the mutation
        # harness in test_phase40e_guard_mutations.py, which is why that file exists.
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "clear my cart")
        for message in (
            "what are your opening hours",
            "delivery",
            "how much is a burger",
            "hmm",
            "thanks",
            "no",
            "nahi karo",
        ):
            with self.subTest(message=message):
                basket = RecordingBasket(two_lines())
                step(basket, message, pending=pending)
                self.assertEqual(basket.mutations, [], message)

    def test_no_message_leaves_a_question_open_for_a_later_ok(self):
        # A proposal lives for exactly one message. Anything else - a question, an
        # unrelated remark, a blocked message - ends it, so there is no sequence of turns
        # after which a stray "ok" resolves something the customer has forgotten.
        for filler in ("what are your hours", "delivery", "do you have cola", "thanks"):
            with self.subTest(filler=filler):
                _s, _p, _r, pending = step(
                    RecordingBasket([]), "i want a zinger burger", matched=[catalog_item()]
                )
                after = step(RecordingBasket([]), filler, pending=pending)[3]
                self.assertEqual(after, {}, filler)

                basket = RecordingBasket([])
                step(basket, "ok", matched=[catalog_item()], pending=after)
                self.assertEqual(basket.mutations, [], filler)

    def test_a_message_that_agrees_and_refuses_is_treated_as_a_refusal(self):
        # An earlier attempt made "both signals" mean "neither", so the proposal stayed
        # armed. That is unsafe in the language this product is actually used in: `karo`
        # is an agreement word, so "nahi karo" - a plain Roman Urdu no - counted as
        # ambiguous, the destructive proposal survived, and a later "ok" applied it.
        #
        # Refusing costs nothing and agreeing costs the cart, so a negative wins and the
        # customer is told how it was read.
        for message in ("yes no onions", "nahi karo", "ji nahi", "ok no", "yes cancel it"):
            with self.subTest(message=message):
                _s, _p, _r, pending = step(
                    RecordingBasket(two_lines()), "clear my cart", matched=[]
                )
                basket = RecordingBasket(two_lines())
                _s, plan, _r, after = step(basket, message, pending=pending)
                self.assertEqual(basket.mutations, [], message)
                self.assertEqual(after, {}, f"{message}: the proposal survived a refusal")
                self.assertTrue(plan["note"], message)


class WhatTheSecondReviewBrokeTests(unittest.TestCase):
    """The second review broke all six repairs the first one prompted.

    Its findings are here as tests because every one of them was a case where the fix was
    right about the thing it named and wrong about its neighbour.
    """

    def setUp(self):
        import app.ai.agents.actions as actions_module
        import app.db.mongodb as mongodb_module

        self._patched = []
        for module in (actions_module, mongodb_module):
            self._patched.append((module, getattr(module, "get_database", None)))
            module.get_database = lambda: _FakeDB()

    def tearDown(self):
        for module, original in self._patched:
            if original is not None:
                module.get_database = original

    def test_a_stored_removal_will_not_land_on_a_line_that_now_holds_something_else(self):
        # A line id can be reused: `find_cart_line` falls back to matching by item, and
        # legacy rows take their line id FROM the item id. The scope check was by id and
        # quantity, so agreeing to "remove the fries" removed whatever had inherited that
        # id - and the reply still said "Removed Fries", because the label came from the
        # stored action rather than from what was touched.
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "remove the fries")
        self.assertEqual([action["verb"] for action in pending["actions"]], ["remove"])

        swapped = RecordingBasket(
            [line("Zinger Burger", "L1"), line("Diamond Ring", "L2", FRIES_ID)]
        )
        _s, _plan, result, _n = step(swapped, "yes", pending=pending)
        self.assertEqual(swapped.mutations, [])
        self.assertEqual(result["blocked"], "awaiting_confirmation")

    def test_a_quantity_change_behind_the_agents_back_forces_a_re_ask(self):
        # "Are you sure? That removes all 1 item(s)" followed by the cart page bumping
        # that one line to forty. Comparing line ids alone saw no change at all.
        _s, _p, _r, pending = step(
            RecordingBasket([line("Zinger Burger", "L1", quantity=1)]), "clear my cart"
        )
        bumped = RecordingBasket([line("Zinger Burger", "L1", quantity=40)])
        step(bumped, "yes", pending=pending)
        self.assertEqual(bumped.mutations, [])

    def test_a_destructive_question_does_not_survive_an_unrelated_message(self):
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "clear my cart")
        self.assertTrue(pending["actions"])
        after = step(RecordingBasket(two_lines()), "what are your opening hours", pending=pending)[3]
        self.assertEqual(after, {})

        basket = RecordingBasket(two_lines())
        step(basket, "ok", pending=after)
        self.assertEqual(basket.mutations, [])

    def test_dropping_a_question_is_never_silent(self):
        # The sentence has to reach the CUSTOMER, not just the plan. Asserting on the plan
        # alone missed that `_basket_reply` returns a clarification INSTEAD of the note.
        _s, _p, _r, pending = step(
            RecordingBasket([]), "i want a zinger burger", matched=[catalog_item()]
        )
        for message in ("delivery", "what are your hours", "yes no onions", "hmm"):
            with self.subTest(message=message):
                _s, plan, actions, _n = step(
                    RecordingBasket(two_lines()), message, pending=pending
                )
                state = SimpleNamespace(
                    basketPlan=plan,
                    basketActions=actions,
                    basket={"isEmpty": False, "lines": []},
                    checkoutReadiness={},
                )
                self.assertTrue(_basket_reply(state).strip(), message)

    def test_a_clock_running_ahead_does_not_make_a_proposal_immortal(self):
        # `now - made <= TTL` is true for every negative age, so a timestamp from a fast
        # instance never expired.
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "clear my cart")
        future = {
            **pending,
            "proposedAt": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        }
        basket = RecordingBasket(two_lines())
        step(basket, "yes", pending=future)
        self.assertEqual(basket.mutations, [])

    def test_an_expired_question_says_so_instead_of_doing_nothing(self):
        # The customer answers the question they were asked and the agent silently does
        # nothing. They have no way to tell that from it having worked.
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "clear my cart")
        expired = {
            **pending,
            "proposedAt": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        }
        basket = RecordingBasket(two_lines())
        _s, plan, _r, _n = step(basket, "yes", pending=expired)
        self.assertEqual(basket.mutations, [])
        self.assertIn("expired", plan["note"].lower())


class WhatTheThirdReviewBrokeTests(unittest.TestCase):
    """The third review broke the invariant twice. Both were about which rows the guard
    covered rather than what it checked, which is the same shape as everything before it.
    """

    def setUp(self):
        import app.ai.agents.actions as actions_module
        import app.db.mongodb as mongodb_module

        self._patched = []
        for module in (actions_module, mongodb_module):
            self._patched.append((module, getattr(module, "get_database", None)))
            module.get_database = lambda: _FakeDB()

    def tearDown(self):
        for module, original in self._patched:
            if original is not None:
                module.get_database = original

    def _live(self, actions, lines):
        return {
            "intent": "remove_from_cart",
            "actions": actions,
            "proposedAt": datetime.now(timezone.utc).isoformat(),
            "reasksLeft": 2,
            "cartScope": sorted(f"{r.lineId}:{r.itemId}:{r.quantity}" for r in lines),
        }

    def test_a_proposal_stored_before_subject_existed_is_not_trusted(self):
        # `subject` is newer than the rows in the database. The guard skipped any action
        # without one, so it was switched off for exactly the population that existed when
        # it shipped: a confirmed "yes" deleted an item the customer had never been shown,
        # and the reply named the old one.
        cart = [line("Zinger Burger", "L1"), line("Diamond Ring", "L2", FRIES_ID)]
        pending = self._live([{"verb": "remove", "lineId": "L2", "label": "Removed Fries"}], cart)
        basket = RecordingBasket(list(cart))
        _s, plan, result, again = step(basket, "yes", pending=pending)
        self.assertEqual(basket.mutations, [])
        self.assertEqual(result["blocked"], "awaiting_confirmation")

        # And the SECOND yes. Stopping at the first re-ask was how the invariant break
        # shipped: the guard fired, the customer was re-asked about "Fries", the proposal
        # was silently refrozen against the Diamond Ring that had taken the line, and the
        # next yes deleted the ring while the reply said "Removed Fries".
        self.assertNotIn("Fries", plan["confirmationPrompt"])
        self.assertIn("Diamond Ring", plan["confirmationPrompt"])

        second = RecordingBasket(list(cart))
        _s, _p, result, _n = step(second, "yes", pending=again)
        for row in result["applied"]:
            self.assertNotIn("Fries", row.get("label") or "")

    def test_two_lines_sharing_an_id_are_never_guessed_between(self):
        # Rows written before line ids existed take their id FROM the item, so two
        # variants of one item collide. The check read the last of them and the write hit
        # the first, so agreeing to remove the blue shirt removed the red one.
        shared = BURGER_ID
        cart = [
            dataclasses.replace(line("Shirt", shared, shared, 1), selectedVariantName="Red"),
            dataclasses.replace(line("Shirt", shared, shared, 1), selectedVariantName="Blue"),
        ]
        pending = self._live(
            [{"verb": "remove", "lineId": shared, "subject": "Shirt (Blue)", "label": "Removed Shirt (Blue)"}],
            cart,
        )
        basket = RecordingBasket(cart)
        step(basket, "yes", pending=pending)
        self.assertEqual(basket.mutations, [])

    def test_a_message_that_merely_contains_no_is_a_request_not_a_refusal(self):
        # `is_negative` is unbounded and is used all over the planner, where that is what
        # is wanted. Resolving a confirmation with it swallowed whole sentences: the
        # customer's actual request was answered "Left your cart as it is" and discarded.
        _s, _p, _r, pending = step(
            RecordingBasket([]), "i want a zinger burger", matched=[catalog_item()]
        )
        # Four tokens as well as five: the bounded test this replaced ate the short ones,
        # and the corpus had been picked to avoid them. Asserting only that the note
        # differs from one exact string was also too weak - the refusal branch has more
        # than one wording - so the test now says what must be true: nothing is written,
        # and the message is not answered as an answer.
        for message in (
            "add fries but no onions",
            "add fries no onions",
            "no onions please",
            "no actually make it 3",
            "cancel my old order please",
            "cancel my order",
            "stop asking, just add it",
        ):
            with self.subTest(message=message):
                basket = RecordingBasket([])
                _s, plan, _r, _n = step(
                    basket, message, matched=[catalog_item()], pending=pending
                )
                self.assertEqual(basket.mutations, [], message)
                self.assertNotIn(
                    plan.get("note") or "",
                    ("Left your cart as it is.",),
                    message,
                )

    def test_a_short_refusal_is_still_a_refusal(self):
        for message in ("no", "nahi", "nahi karo", "no thanks", "mat karo"):
            with self.subTest(message=message):
                _s, _p, _r, pending = step(RecordingBasket(two_lines()), "clear my cart")
                basket = RecordingBasket(two_lines())
                step(basket, message, pending=pending)
                self.assertEqual(basket.mutations, [], message)

    def test_a_quantity_proposal_does_not_survive_an_unrelated_turn(self):
        # "make it 1" against a cart of forty destroys thirty-nine units. That it is not
        # spelled `remove` does not make it recoverable.
        _s, _p, _r, pending = step(
            RecordingBasket([line("Zinger Burger", "L1", quantity=40)]), "make it 1"
        )
        self.assertEqual([action["verb"] for action in pending["actions"]], ["set_quantity"])
        after = step(
            RecordingBasket([line("Zinger Burger", "L1", quantity=40)]),
            "what are your opening hours",
            pending=pending,
        )[3]
        self.assertEqual(after, {})

    def test_a_target_the_customer_deleted_ends_the_question(self):
        # Re-asking about a line that no longer exists is a question with no answer. It
        # repeated until the proposal timed out half an hour later.
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "remove the fries")
        gone = RecordingBasket([line("Zinger Burger", "L1")])
        _s, plan, result, after = step(gone, "yes", pending=pending)
        self.assertEqual(gone.mutations, [])
        self.assertEqual(after, {})
        self.assertNotEqual(result["blocked"], "awaiting_confirmation")
        self.assertIn("not in your cart", plan["note"])

    def test_a_renamed_item_is_re_asked_once_and_then_answerable(self):
        # The re-ask kept comparing against the old label, so the condition causing it was
        # permanent and the budget never counted down.
        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "remove the fries")
        renamed = [line("Zinger Burger", "L1"), line("Pommes Frites", "L2", FRIES_ID)]

        basket = RecordingBasket(list(renamed))
        _s, plan, result, again = step(basket, "yes", pending=pending)
        self.assertEqual(basket.mutations, [])
        self.assertEqual(result["blocked"], "awaiting_confirmation")

        # The question must name what the next yes will actually do. No test compared the
        # two before, which is how a prompt saying "Fries" came to store an action
        # pointing at something else.
        self.assertIn("Pommes Frites", plan["confirmationPrompt"])
        self.assertEqual(
            [action["subject"] for action in again["actions"]], ["Pommes Frites"]
        )

        # Re-described, so the next yes resolves rather than asking a third time.
        second = RecordingBasket(list(renamed))
        _s, _p, result, _n = step(second, "yes", pending=again)
        self.assertEqual(second.mutations, [("remove", "Pommes Frites")])
        self.assertEqual(
            [row["label"] for row in result["applied"]], ["Removed Pommes Frites"]
        )


class WhatTheFourthReviewBrokeTests(unittest.TestCase):
    """The fourth review broke the invariant through the repair for the third one."""

    def setUp(self):
        import app.ai.agents.actions as actions_module
        import app.db.mongodb as mongodb_module

        self._patched = []
        for module in (actions_module, mongodb_module):
            self._patched.append((module, getattr(module, "get_database", None)))
            module.get_database = lambda: _FakeDB()

    def tearDown(self):
        for module, original in self._patched:
            if original is not None:
                module.get_database = original

    def test_a_refusal_longer_than_an_answer_still_ends_the_question(self):
        # A bounded refusal test misses "nahi bhai abhi rehne do" and the proposal stayed
        # armed, so the agent nagged a customer who had refused and a later "ok" added the
        # thing they turned down. Whether the refusal is ANNOUNCED and whether the
        # proposal SURVIVES are now two separate decisions.
        for refusal in (
            "nahi bhai abhi rehne do",
            "nahi mujhe ye nahi chahiye ab",
            "no i dont want that any more",
            "no thanks, leave it as it is",
            "don't",
            "do not",
            "please don't",
            "not now",
            "never mind",
            "forget it",
            "nah",
            "changed my mind",
            "skip it",
            "i'd rather not",
        ):
            with self.subTest(refusal=refusal):
                _s, _p, _r, pending = step(
                    RecordingBasket([]), "i want a zinger burger", matched=[catalog_item()]
                )
                basket = RecordingBasket([])
                _s, _p, _r, after = step(basket, refusal, pending=pending)
                self.assertEqual(basket.mutations, [], refusal)
                self.assertEqual(after, {}, refusal)

                later = RecordingBasket([])
                step(later, "ok", matched=[catalog_item()], pending=after)
                self.assertEqual(later.mutations, [], refusal)

    def test_the_apply_flag_is_set_at_the_write_not_after_it(self):
        # The caller restores a claimed proposal when a turn dies. Recording the write
        # after `_run_basket_step` returned meant a failure in `basket.summary()` - which
        # runs immediately after the write - looked like "nothing happened", so the
        # proposal was restored and the retry applied it twice.
        class FailingSummaryBasket(RecordingBasket):
            async def summary(self):
                if self.mutations:
                    raise RuntimeError("summary failed after the write")
                return await RecordingBasket.summary(self)

        _s, _p, _r, pending = step(RecordingBasket(two_lines()), "clear my cart")
        outcome: dict = {}
        basket = FailingSummaryBasket(two_lines())
        with self.assertRaises(RuntimeError):
            asyncio.run(_run_basket_step(basket, "yes", [], pending, outcome))
        self.assertTrue(basket.mutations)
        self.assertIs(outcome.get("basketApplied"), True)

    def test_a_connective_does_not_bridge_a_word_that_means_something(self):
        # "get", "have", "some", "of" and "me" were treated as meaningless, so "i want to
        # GET THE delivery status" was a request for delivery.
        for message in (
            "i want to get the delivery status",
            "please get me the delivery address",
            "i want to get some of the cash back",
            "i would have some of the cash",
            "please have some of the bank details",
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    extract_checkout_details(
                        message,
                        allowed_fields={"fulfillmentType", "paymentMethod"},
                        revisable_fields=set(),
                    ),
                    {},
                    message,
                )

    def test_ordinary_ways_of_choosing_are_not_lost(self):
        for message, field, value in (
            ("i will pay using jazzcash", "paymentMethod", "jazzcash"),
            ("i will pay through easypaisa", "paymentMethod", "easypaisa"),
            ("ill take pickup", "fulfillmentType", "pickup"),
            ("please send it to my home", "fulfillmentType", "delivery"),
            ("i want it delivered", "fulfillmentType", "delivery"),
        ):
            with self.subTest(message=message):
                got = extract_checkout_details(
                    message,
                    allowed_fields={"fulfillmentType", "paymentMethod"},
                    revisable_fields=set(),
                )
                self.assertEqual(got.get(field), value, message)


class CheckoutDetailsAnswerAQuestionTests(unittest.TestCase):
    """AI-07: a detail is recorded only for a field the agent asked about."""

    BOTH = {"fulfillmentType", "paymentMethod"}

    REMARKS = [
        "the delivery guy was rude",
        "my bank is closed today",
        "do you accept cash",
        "do you deliver",
        "why is delivery so slow",
        "can i get cash on delivery",
        "my friend paid by jazzcash last time",
        "i dont have cash",
        "delivery was late",
        "bank is closed",
        "your delivery charges are too high",
    ]

    ANSWERS = [
        ("cash on delivery", "paymentMethod", "cod"),
        ("jazzcash", "paymentMethod", "jazzcash"),
        ("easypaisa please", "paymentMethod", "easypaisa"),
        ("i want delivery", "fulfillmentType", "delivery"),
        ("pickup", "fulfillmentType", "pickup"),
        ("khud aunga", "fulfillmentType", "pickup"),
        ("ghar bhej do", "fulfillmentType", "delivery"),
    ]

    # Sentences that mention a choice without making one. These are the AI-07 bug: each
    # one used to set a checkout field, after which readiness reported the order ready to
    # place with details the customer never chose.
    PASSING_MENTIONS = [
        "my friend paid by jazzcash last time",
        "the delivery guy was rude",
        "delivery was late",
        "bank is closed",
        "my bank is closed today",
        "i dont have cash",
        "your delivery charges are too high",
    ]

    # Deliberate corrections to a choice already on file.
    CORRECTIONS = [
        ("actually jazzcash", "paymentMethod", "jazzcash"),
        ("i want to pay with jazzcash", "paymentMethod", "jazzcash"),
        ("jazzcash", "paymentMethod", "jazzcash"),
        ("actually pickup", "fulfillmentType", "pickup"),
        ("i want pickup instead", "fulfillmentType", "pickup"),
    ]

    def test_a_remark_records_nothing_whatever_the_agent_is_waiting_for(self):
        # The state of `allowed_fields` must not rescue a sentence that never made a
        # choice. Checked in all three states: nothing outstanding, both fields
        # outstanding, and one of each.
        for message in self.REMARKS + self.PASSING_MENTIONS:
            for waiting in (set(), self.BOTH, {"paymentMethod"}, {"fulfillmentType"}):
                with self.subTest(message=message, waiting=sorted(waiting)):
                    # Both doors open: whatever is not being asked for is already
                    # answered, so the revision path is available too. Leaving
                    # `revisable_fields` unset made a quarter of these subtests pass for
                    # any sentence at all, because nothing was writable.
                    self.assertEqual(
                        extract_checkout_details(
                            message,
                            allowed_fields=waiting,
                            revisable_fields=self.BOTH - waiting,
                        ),
                        {},
                        message,
                    )

    def test_a_choice_already_on_file_can_still_be_corrected(self):
        # The regression the review caught. An answered field is never in `missingFields`,
        # so gating on that list alone made every recorded choice permanent and the
        # customer was told nothing. A correction is not a passing mention and must land.
        for message, field, value in self.CORRECTIONS:
            with self.subTest(message=message):
                # Nothing is being asked for; this field already holds an answer.
                got = extract_checkout_details(
                    message, allowed_fields=set(), revisable_fields={field}
                )
                self.assertEqual(got.get(field), value, message)

    def test_a_remark_records_nothing_even_while_the_field_is_being_asked_about(self):
        # Defence in depth. The sentence tests were not quietly abandoned when the field
        # gate was added, because the field gate is open exactly when the risk is highest.
        for message in self.REMARKS:
            with self.subTest(message=message):
                self.assertEqual(extract_checkout_details(message, allowed_fields=self.BOTH), {})

    def test_a_real_answer_to_a_real_question_is_still_recorded(self):
        for message, field, value in self.ANSWERS:
            with self.subTest(message=message):
                got = extract_checkout_details(message, allowed_fields=self.BOTH)
                self.assertEqual(got.get(field), value, message)

    def test_a_choice_word_needs_a_request_beside_it_not_anywhere_in_the_sentence(self):
        # `asks_in_words` searched the whole message, so "i want" five words away from a
        # noun made that noun a choice. These all name a real option and choose none.
        for message in (
            "i want to complain about delivery",
            "lets talk about delivery",
            "i want to know if you deliver",
            "please pay the delivery guy",
            "i would rather not talk about the bank",
        ):
            for waiting in (set(), self.BOTH):
                with self.subTest(message=message, waiting=sorted(waiting)):
                    self.assertEqual(
                        extract_checkout_details(
                            message,
                            allowed_fields=waiting,
                            revisable_fields=self.BOTH - waiting,
                        ),
                        {},
                        message,
                    )

    def test_an_empty_cart_is_not_a_checkout_in_progress(self):
        # `missingFields` gates the harvester, and reporting both fields outstanding for
        # an empty cart held that gate open from the first message of every conversation,
        # which is most of why it was not stopping anything.
        self.assertEqual(
            checkout_readiness({"isEmpty": True, "itemCount": 0}, {}, has_account=True)["missingFields"],
            [],
        )

    def test_a_perfectly_phrased_answer_is_still_refused_when_nothing_was_asked(self):
        # The gate that makes AI-07 structural rather than another word list. Every other
        # test here uses a sentence the WORD tests reject, so removing the gate entirely
        # left the suite green - found by the mutation harness. These sentences pass the
        # word tests and must still be refused, because no question is open.
        for message, field in (
            ("pickup", "fulfillmentType"),
            ("cash on delivery", "paymentMethod"),
            ("jazzcash", "paymentMethod"),
            ("i want delivery", "fulfillmentType"),
            ("khud aunga", "fulfillmentType"),
        ):
            with self.subTest(message=message):
                self.assertTrue(
                    extract_checkout_details(message, allowed_fields={field}, revisable_fields=set()),
                    f"{message} should be a valid answer when the field is asked about",
                )
                self.assertEqual(
                    extract_checkout_details(message, allowed_fields=set(), revisable_fields=set()),
                    {},
                    message,
                )

    def test_readiness_names_the_fields_it_is_waiting_for(self):
        # If it did not, the gate above could never open and checkout would be
        # unreachable. This is the test that stops the AI-07 fix from bricking checkout.
        waiting = checkout_readiness({"isEmpty": False, "itemCount": 1}, {}, has_account=True)
        self.assertEqual(set(waiting["missingFields"]), self.BOTH)

        ready = checkout_readiness(
            {"isEmpty": False, "itemCount": 1},
            {"fulfillmentType": "pickup", "paymentMethod": "cod"},
            has_account=True,
        )
        self.assertEqual(ready["missingFields"], [])
        self.assertTrue(ready["canCheckout"])


if __name__ == "__main__":
    unittest.main()
