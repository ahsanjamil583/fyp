"""Does the suite actually hold the guards it names?

Five adversarial reviews of the agent write gate found, between them, nine assertions that
could not fail. Three of them guarded the exact defect that later shipped. The pattern was
always the same: a test written per-SENTENCE against a word list, which passes whether or
not the guard it is named for exists.

So this file tests the tests. Each entry below disables one guard and asserts that the
suite notices. It is the cheapest possible version of mutation testing - a source
substitution, a re-import, and a re-run of the one test file - and it would have caught
every one of those nine.

Nothing here is a mutation of the repository. The source is rewritten in memory, compiled
into a throwaway module, and patched over the real one for the duration of a single test.
"""

import contextlib
import importlib
import os
import sys
import types
import unittest
from unittest import mock


def _load_mutant(module_name: str, replacements: list[tuple[str, str]]) -> types.ModuleType:
    """Compile a copy of `module_name` with each `old` replaced by `new`."""
    original = importlib.import_module(module_name)
    with open(original.__file__, encoding="utf-8") as handle:
        source = handle.read()
    for old, new in replacements:
        assert source.count(old) == 1, f"mutation anchor not unique in {module_name}: {old!r}"
        source = source.replace(old, new, 1)
    mutant = types.ModuleType(module_name)
    mutant.__file__ = original.__file__
    mutant.__dict__["__name__"] = module_name
    exec(compile(source, original.__file__, "exec"), mutant.__dict__)
    return mutant


def _suite_notices(module_name: str, replacements: list[tuple[str, str]]) -> bool:
    """Run the write-gate tests against a mutated module. True if anything fails."""
    mutant = _load_mutant(module_name, replacements)
    target = sys.modules["tests.test_phase40e_agent_write_gate"]
    # `from x import y` binds the function into the importing module, so replacing the
    # module in sys.modules is not enough: every module that already pulled a name out of
    # it still holds the original. The first version of this harness missed that and
    # reported a guard as held when the mutation had not reached the code under test.
    consumers = [target, sys.modules[ORCHESTRATOR], sys.modules[ACTIONS]]
    stack = [mock.patch.dict(sys.modules, {module_name: mutant})]
    for consumer in consumers:
        if consumer.__name__ == module_name:
            continue
        shared = {
            name: getattr(mutant, name)
            for name in dir(mutant)
            if not name.startswith("__") and hasattr(consumer, name)
        }
        if shared:
            stack.append(mock.patch.multiple(consumer, **shared))
    with contextlib.ExitStack() as active:
        for patcher in stack:
            active.enter_context(patcher)
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(target)
        with open(os.devnull, "w") as quiet:
            result = unittest.TextTestRunner(stream=quiet, verbosity=0).run(suite)
    return not result.wasSuccessful()


ORCHESTRATOR = "app.ai.agents.orchestrator_agent"
ACTIONS = "app.ai.agents.actions"


class TheSuiteHoldsTheGuardsItNamesTests(unittest.TestCase):
    """Each of these disables one guard. The suite must fail."""

    def setUp(self):
        # These tests re-run the whole write-gate file several times over; skip them under
        # a narrowed selection so a focused run stays fast.
        importlib.import_module("tests.test_phase40e_agent_write_gate")

    def test_the_suite_notices_if_the_confirmation_classifier_always_says_yes(self):
        self.assertTrue(
            _suite_notices(
                ACTIONS,
                [("def classify_confirmation_answer(message_text: str) -> str:",
                  "def classify_confirmation_answer(message_text: str) -> str:\n    return YES")],
            )
        )

    def test_the_suite_notices_if_a_refusal_is_read_as_unclear(self):
        # NO and UNCLEAR are handled identically by the caller, so this one is ALLOWED to
        # pass: the assertion is that nothing dangerous happens either way. It is here to
        # document that the equivalence is deliberate rather than accidental.
        notices = _suite_notices(
            ACTIONS,
            [('        return NO if not remainder else UNCLEAR', '        return UNCLEAR')],
        )
        self.assertFalse(
            notices,
            "NO and UNCLEAR are meant to be interchangeable for safety; if this now fails, "
            "something has come to depend on the difference and that dependency needs a "
            "deliberate look.",
        )

    def test_the_suite_notices_if_the_target_identity_check_is_disabled(self):
        self.assertTrue(
            _suite_notices(
                ORCHESTRATOR,
                [("def _targets_have_moved(proposed, lines) -> bool:",
                  "def _targets_have_moved(proposed, lines) -> bool:\n    return False")],
            )
        )

    def test_the_suite_notices_if_the_cart_scope_ignores_quantities(self):
        self.assertTrue(
            _suite_notices(
                ORCHESTRATOR,
                [('return sorted(f"{line.lineId}:{line.itemId}:{line.quantity}" for line in lines)',
                  'return sorted(f"{line.lineId}:{line.itemId}" for line in lines)')],
            )
        )

    def test_the_suite_notices_if_a_proposal_never_expires(self):
        self.assertTrue(
            _suite_notices(
                ORCHESTRATOR,
                [("def _proposal_is_live(pending: dict[str, Any]) -> bool:",
                  "def _proposal_is_live(pending: dict[str, Any]) -> bool:\n    return True")],
            )
        )

    def test_the_suite_notices_if_the_re_ask_stops_re_describing(self):
        self.assertTrue(
            _suite_notices(
                ORCHESTRATOR,
                [("def _redescribe(proposed, lines):",
                  "def _redescribe(proposed, lines):\n    return list(proposed)")],
            )
        )

    def test_the_suite_notices_if_the_checkout_field_gate_is_removed(self):
        # The gate that makes AI-07 structural rather than a word list. A previous review
        # found that deleting it left the whole suite green.
        self.assertTrue(
            _suite_notices(
                ACTIONS,
                [('    def may_write(field: str, phrases) -> bool:\n        """Whether this message is entitled to set `field`."""',
                  '    def may_write(field: str, phrases) -> bool:\n        """Whether this message is entitled to set `field`."""\n        return True')],
            )
        )

    def test_the_suite_notices_if_the_bare_answer_test_is_removed(self):
        self.assertTrue(
            _suite_notices(
                ACTIONS,
                [("def _is_bare_answer(normalized: str, phrases: tuple[str, ...] | set[str] = ()) -> bool:",
                  "def _is_bare_answer(normalized: str, phrases: tuple[str, ...] | set[str] = ()) -> bool:\n    return True")],
            )
        )

    def test_the_suite_notices_if_a_proposal_is_applied_without_being_stored(self):
        # The core invariant, clause one. Turning the propose-then-return into a write is
        # the single most important thing this suite has to catch.
        self.assertTrue(
            _suite_notices(
                ORCHESTRATOR,
                [("    if plan.actions:\n        described", "    if False:\n        described")],
            )
        )


if __name__ == "__main__":
    unittest.main()
