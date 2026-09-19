"""Deciding what to do to the basket, and doing it.

Split in two on purpose:

``plan_basket_actions``
    Reads the message and the current basket and returns *what should happen*. Pure:
    no database, no clock, no writes. Every branch is unit-testable, and a future
    LLM planner can replace this function alone as long as it returns the same
    ``BasketPlan``.
``execute_basket_actions``
    Applies a plan, re-validating every action against the live catalog before it
    touches anything.

The split matters because these actions auto-apply. A planner that guesses wrong writes
to a real cart, so two rules run through the whole module:

* **Never guess when it matters.** If the message could mean two different lines, the
  plan carries a ``clarification`` and no actions. Asking is cheap; silently changing
  the wrong line is not.
* **The planner cannot invent an item.** It may only name something the catalog search
  surfaced this turn or something already in the basket. The executor enforces that
  independently, so a bug in the planner cannot become a wrong write.

Clearing is the one destructive verb, so it is never applied on the first ask: the plan
comes back asking for confirmation, and only a plan built from an explicit "yes" clears
anything.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.agents.tools import (
    ORDER_HINTS,
    extract_numeric_quantity,
    extract_quantity,
    normalize_message_text,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ basket intents --

ADD = "add_to_cart"
REMOVE = "remove_from_cart"
UPDATE = "update_quantity"
VIEW = "view_cart"
CLEAR = "clear_cart"
CHECKOUT = "checkout"
NONE = "none"

BASKET_INTENTS = (ADD, REMOVE, UPDATE, VIEW, CLEAR, CHECKOUT, NONE)

# Roman Urdu sits beside English throughout, matching how the existing classifier works.
REMOVE_HINTS = {
    "remove", "delete", "drop", "cancel", "nikal", "nikalo", "nikaldo", "hata", "hatao",
    "hatado", "hatana",
}

# These used to sit in REMOVE_HINTS, which meant "burger without onions" and "fries
# without salt" deleted the item instead of ordering it. They describe how the customer
# wants something made; they never act on the cart. Kept as their own set so a message
# built only out of them is recognised as a modifier rather than an instruction.
MODIFIER_HINTS = {"without", "less", "minus", "bina", "no onions", "extra", "light"}
UPDATE_HINTS = {
    "change", "update", "make", "set", "instead", "badal", "badlo", "badal do", "kardo",
    "kar do", "increase", "decrease", "barha", "kam",
}
VIEW_HINTS = {
    "cart", "basket", "trolley", "list", "summary", "total", "dikhao", "dikhado",
    "batao", "kya hai", "whats in",
}
CLEAR_HINTS = {
    "clear", "empty", "reset", "khali", "sab hata", "sab nikal", "remove all", "delete all",
    "start over", "cancel everything", "cancel all",
}
CHECKOUT_HINTS = {
    "checkout", "place order", "place my order", "confirm order", "order karo", "order kardo",
    "order kar do", "proceed", "finalize", "finalise", "complete order", "order confirm",
    "buy now", "pay now", "order place",
}
# ORDER_HINTS covers "order/buy/chahiye" but not the plainest word of all. Without these
# "also add fries" matched no verb and the planner did nothing.
#
# Split by strength, because these write to a real cart. A strong hint only makes sense
# as an instruction to add something. A weak one appears just as often in a question:
# "where can I GET the burger", "tell me MORE about it". A weak hint alone is not enough.
STRONG_ADD_HINTS = ORDER_HINTS | {
    "add", "want", "need", "include", "dedo", "dena", "daal", "daldo", "dal do", "shamil",
    "bhejo", "bhej", "bhejdo", "bhej do",
}
WEAK_ADD_HINTS = {"get", "take", "plus", "also", "another", "more"}
ADD_HINTS = STRONG_ADD_HINTS | WEAK_ADD_HINTS

# Markers that make a message a question rather than an instruction. A bare number in
# "is the burger under 500?" is a budget, not a quantity.
QUESTION_HINTS = {
    "what", "whats", "which", "how", "how much", "how many", "where", "when", "why",
    "do you", "does", "is it", "is the", "are they", "tell me", "is there", "is possible",
    "kya", "kitna", "kitne", "kahan", "kab", "kaise", "kaisa", "kaisi", "kesa",
    "price", "cost", "rate", "charge",
    "charges", "fee", "free", "available", "availability", "batao", "bata", "policy",
    # "I need to know whether you have burgers" carries an add hint ("need") but is
    # plainly an enquiry. The phrase settles it whatever verb precedes it.
    "to know", "if you have", "whether you",
}

# Markers of a hypothetical: the customer is asking whether something is possible, or
# about some future occasion, rather than asking for it now. These override everything,
# including a polite-request shape. "Can I remove an item later?" is a question about how
# the shop works, and answering it by deleting a line is the worst available reading.
# Openers that introduce a description rather than a request: "there are four people
# here and one burger" states a fact and orders nothing.
STATEMENT_HINTS = {"there are", "there is", "there was", "there were", "we are", "i am"}

HYPOTHETICAL_HINTS = {
    "later", "afterwards", "after i", "after placing", "if i", "if we", "in future",
    "next time", "able to", "possible to", "allowed to", "still able", "would i",
    "baad mein", "baad me",
    # Modal and past forms. Someone describing an intention, a habit or something they
    # nearly did is not instructing anything: "I was going to remove the fries",
    # "we usually remove items before paying", "maybe I should clear it".
    "was going", "were going", "about to", "going to", "planning", "plan to", "thinking",
    "wondering", "might", "maybe", "perhaps", "should i", "should you", "could have",
    "wanted to", "used to", "last time", "usually", "someone told", "suppose", "agar",
    "i may", "we may",
    # Past tense describes what happened, not what should happen now: "I had ordered two
    # burgers" is context for a question, not a request for two more.
    "had ordered", "have ordered", "already ordered", "i had", "we had", "yesterday",
}

# Spelled-out quantities. Only digits were counted, so "one burger please" and
# "i'll take two burgers" looked like they carried no quantity and did nothing at all.
SPELLED_QUANTITIES = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    # Roman Urdu is spelled inconsistently in practice, so both spellings of each.
    "ek", "aik", "ak", "teen", "char", "chaar", "panch", "paanch", "chay", "cheh",
    "saat", "sat", "aath", "nau", "das",
}

# Deliberately NOT in SPELLED_QUANTITIES. "a" and "an" are articles: counting them made
# "there was a hair in the burger" an order for one burger. Urdu "do" is both the number
# two and the verb "give", so "i do not like the burger" ordered two. They count only
# when an add verb is also present, which is checked separately.
AMBIGUOUS_QUANTITIES = {"a", "an", "do"}

# Imported, not redeclared. A second copy of this number is how the cashier schema came
# to advertise 999 while the order builder refused anything over 99.
from app.services.smart_order_service import MAX_LINE_QUANTITY  # noqa: E402

# English asks for things by pretending to ask a question. "Can I get two burgers?" is an
# order, not an enquiry, and treating every interrogative as a question silently turned
# the most common polite phrasing into a no-op. These are the shapes where an
# interrogative opener is followed by an action verb, which makes it a request.
# Only ACQUISITION verbs appear here. Destructive verbs are deliberately absent: a polite
# shape must never turn a question into a deletion. "Can you remove the burger" is still
# recognised, because it is not question-shaped to begin with and so never needs a bypass.
POLITE_REQUEST_PATTERNS = (
    re.compile(
        r"\b(?:can|could|may|would|will)\s+(?:i|we|you|u)\s+(?:please\s+)?"
        r"(?:get|have|take|order|add|put|make|give|send|bring|buy)\b"
    ),
    re.compile(r"\bi\s+d\s+like\b"),
    re.compile(r"\bi\s+(?:would|will|ll)\s+(?:like|take|have)\b"),
    # "I want to KNOW the price" is a question. Only an acquisition verb after the modal
    # makes it a request, which is why this verb list is explicit rather than open-ended.
    re.compile(r"\bi\s+(?:wanna|want|need|wish)\s+(?:to\s+)?(?:order|buy|get|have|take|add)\b"),
    re.compile(r"\bplease\s+(?:add|order|get|make|send|put)\b"),
    re.compile(r"\b(?:gimme|lemme|gib)\b"),
    re.compile(r"\ble\s+lo\b"),
    # Roman Urdu: "mujhe do burger chahiye", "kya mujhe burger mil sakta hai".
    re.compile(r"\bmujhe\b.*\b(?:chahiye|chahiyen|mil|dedo|de do|dena)\b"),
)

AFFIRMATIVE_HINTS = {
    "yes", "yeah", "yep", "yup", "ya", "y", "k", "sure", "ok", "okay", "okey", "kk",
    "haan", "han", "ha", "hn", "hanji", "ji", "jee", "g", "confirm", "confirmed",
    "karo", "kardo", "krdo", "bilkul", "theek", "thik", "sahi", "acha", "accha", "achha",
    "done", "perfect", "great", "absolutely", "please", "proceed", "go", "ahead",
    "do", "good", "sounds", "fine", "cool", "alright", "chalo",
}
NEGATIVE_HINTS = {"no", "nope", "nahi", "nahin", "cancel", "rehne", "chodo", "mat", "dont", "stop"}
# Refusals, as opposed to words that merely appear in NEGATIVE_HINTS. "cancel" and
# "stop" are in that set but are themselves destructive verbs, so treating them as a
# refusal would make "cancel everything" mean its own opposite.
#
# These are patterns rather than tokens because normalize_message_text strips the
# apostrophe: "don't" arrives as "don t", so a "dont" token never matched anything.
REFUSAL_PATTERNS = (
    re.compile(r"\b(?:no|nope|nahi|nahin|mat|rehne|chodo)\b"),
    re.compile(r"\bdon\s+t\b"),
    re.compile(r"\bdo\s+not\b"),
    re.compile(r"\bdont\b"),
    # The apostrophe may or may not be typed, so both spellings of each contraction.
    re.compile(r"\bcan\s*t\b"),
    re.compile(r"\bcant\b"),
    re.compile(r"\bwon\s*t\b"),
    re.compile(r"\bwont\b"),
    re.compile(r"\bcannot\b"),
    re.compile(r"\bunable\b"),
    re.compile(r"\bnot\b"),
    re.compile(r"\bleave it\b"),
    re.compile(r"\bchanged my mind\b"),
)

# "make it 3" / "3 kar do" - a bare quantity with no item named.
BARE_QUANTITY_PATTERNS = (
    re.compile(r"\bmake\s+(?:it|them)\s+(\d{1,3})\b"),
    re.compile(r"\bset\s+(?:it|them)?\s*(?:to\s+)?(\d{1,3})\b"),
    re.compile(r"\bchange\s+(?:it|them)?\s*(?:to\s+)?(\d{1,3})\b"),
    re.compile(r"\b(\d{1,3})\s+kar\s+do\b"),
    re.compile(r"\b(\d{1,3})\s+kardo\b"),
)


def _contains_phrase(normalized: str, hints: set[str]) -> bool:
    """Match multi-word hints as phrases and single words as tokens.

    Token-only matching turned "place order" into a hit on "order" alone, which made
    every "I want to order a burger" look like a checkout request.
    """
    tokens = set(normalized.split())
    for hint in hints:
        if " " in hint:
            if hint in normalized:
                return True
        elif hint in tokens:
            return True
    return False


# A message opening with one of these is asking for information, whatever follows it.
# "where can I get the zinger burger" contains "can i get" but is not an order.
INFORMATIONAL_OPENERS = (
    "what", "where", "when", "why", "how", "which", "who", "whats",
    # Yes/no openers. Deliberately excludes "can" and "could", which are how people
    # place a polite order.
    # "kya" is deliberately absent: it opens a yes/no question AND prefixes a polite
    # request ("kya mujhe do burger mil sakte hain" = "can I get two burgers"). It stays
    # in QUESTION_HINTS, which a polite-request match is allowed to override.
    "is", "are", "was", "were", "does", "did", "has", "have",
)

# The verb is being quoted or described rather than used. "She said remove the fries" is
# a report, and "saying remove deletes it right" is a question about the assistant.
REPORTED_SPEECH_HINTS = {
    "said", "says", "saying", "told", "telling", "quote", "unquote", "asked", "asks",
    "means", "meaning", "word", "kaha", "bola", "kehta", "kehte",
    # Describing the act of using the assistant rather than using it: "typing add 2
    # burgers would order them, right?"
    "typing", "type", "writing", "pressing", "clicking", "button",
}

# Nouns that make a request one for information rather than for goods. "Send me the
# burger recipe" uses an ordering verb but asks for a document.
INFORMATION_NOUNS = {
    "recipe", "menu", "details", "detail", "info", "information", "list", "address",
    "hours", "timing", "timings", "number", "link", "receipt", "invoice", "catalogue",
    "catalog", "brochure", "tareeka", "tarika",
}


# Phrases built from an acquisition verb that mean the opposite of acquiring.
FALSE_FRIEND_PHRASES = ("get rid", "take off", "take out", "take away", "do away")


def _is_polite_request(normalized: str) -> bool:
    """An interrogative that is really an instruction: "can I get two burgers"."""
    if any(phrase in normalized for phrase in FALSE_FRIEND_PHRASES):
        # "Can I get rid of the burger" is a removal wearing an ordering verb.
        return False
    first_word = normalized.split(" ", 1)[0] if normalized else ""
    if first_word in INFORMATIONAL_OPENERS:
        return False
    if _contains_phrase(normalized, HYPOTHETICAL_HINTS):
        # "Can I get a refund later?" asks about policy, not for a refund.
        return False
    return any(pattern.search(normalized) for pattern in POLITE_REQUEST_PATTERNS)


# Tokens that negate the verb they sit in front of. "t" is here because
# normalize_message_text turns "don't" into "don t".
_NEGATION_TOKENS = {
    "not", "t", "dont", "nahi", "nahin", "mat", "never", "bina",
    # normalize_message_text strips apostrophes, so both spellings of each contraction.
    "cant", "cannot", "wont", "couldnt", "shouldnt", "wouldnt", "didnt", "refuse",
}


def _is_refusal(normalized: str) -> bool:
    """Whether the message asks for something NOT to happen."""
    return any(pattern.search(normalized) for pattern in REFUSAL_PATTERNS)


def _negates(normalized: str, hints: set[str]) -> bool:
    """Whether a verb from `hints` is directly negated: "don't add the burger".

    Only the words immediately in front of the verb count. "No onions, add a burger" is
    an order with a note attached, not a refusal, so a bare "no" further back is ignored.
    """
    tokens = normalized.split()
    for index, token in enumerate(tokens):
        if token not in hints:
            continue
        if index >= 1 and tokens[index - 1] in _NEGATION_TOKENS:
            return True
        if index >= 2 and tokens[index - 2] in _NEGATION_TOKENS:
            return True
    return False


def _is_direct_instruction(normalized: str, hints: set[str]) -> bool:
    """Whether a verb from `hints` is given as a plain order rather than discussed.

    True for "remove the fries", "please remove the fries", "fries hata do" - the verb
    sits at the front, optionally behind a politeness word or the thing being acted on.
    False for "I might remove the fries" or "should you remove the fries", where the verb
    is embedded in a sentence about the action rather than a request to perform it.

    This is what lets the destructive paths stop depending on having enumerated every
    hedge: anything that is not a direct order is confirmed rather than applied.
    """
    tokens = normalized.split()
    if not tokens:
        return False

    # Anything that frames the verb as something other than an order disqualifies it,
    # wherever it appears: "she said remove the fries", "saying remove deletes it".
    if _contains_phrase(normalized, REPORTED_SPEECH_HINTS):
        return False

    # Words that may precede an imperative without changing that it is one. Greetings are
    # included because "hi, please remove the fries" is still plainly an instruction.
    skippable = {
        "please", "pls", "plz", "ok", "okay", "abhi", "zara", "just", "so", "then",
        "hi", "hey", "hello", "salam", "assalam", "yaar", "bhai", "actually", "and",
    }
    # The verb must lead the sentence, allowing for politeness and for the object being
    # named first ("the large fries remove", "fries hata do"). Everything the object may
    # be is bounded by looking only at a short prefix.
    for index, token in enumerate(tokens[:6]):
        if token in skippable:
            continue
        if token in hints:
            return True
        # The object may be stated before the verb, but the verb has to follow closely.
        window = tokens[index + 1 : index + 4]
        if any(later in hints for later in window):
            return True
        break
    return False


# Words that stand in for the item the customer just talked about.
ANAPHORA_HINTS = {"it", "that", "this", "them", "those", "these", "ye", "yeh", "wo", "woh", "isko", "usko"}


def _refers_to_the_only_line(normalized: str) -> bool:
    """Whether a removal actually points at the single line in the cart.

    True for "remove it", "hata do", and a bare "remove" - all of which can only mean the
    one thing in the basket. False for "cancel the meeting", which merely contains the
    verb and would otherwise delete that line.
    """
    ignorable = {
        "please", "pls", "the", "my", "from", "cart", "basket",
        # Roman Urdu auxiliaries: "hata do", "nikal dein" are the verb plus a helper.
        "do", "de", "dein", "den", "dijiye", "kar", "karo",
    }
    tokens = [token for token in normalized.split() if token not in ignorable]
    if not tokens:
        return False
    # "remove none of it" and "delete nothing" name the verb in order to decline it.
    if set(tokens) & {"none", "nothing", "nil", "koi", "kuch"}:
        return False
    # Nothing but the verb itself.
    if all(token in REMOVE_HINTS for token in tokens):
        return True
    # The verb plus a pronoun, and NOTHING else. "Remove the pickles from it" names
    # something that is not the line, so it is a change to the item rather than a
    # request to delete it, and deleting the line is not what was asked.
    remainder = set(tokens) - REMOVE_HINTS - ANAPHORA_HINTS
    return not remainder and bool(set(tokens) & ANAPHORA_HINTS) and bool(set(tokens) & REMOVE_HINTS)


# Words that carry no meaning of their own in an order: politeness, articles, joiners
# and the modifiers that describe how an item should be made.
_ORDER_FILLER = {
    "please", "pls", "plz", "ka", "ki", "ke", "aur", "and", "the", "a", "an",
    "my", "for", "me", "with", "extra", "some", "bhi", "too", "also",
}


def _word_matches_item(token: str, item_words: set[str]) -> bool:
    """Whether a token names the item, tolerating plurals and short suffixes."""
    if len(token) < 3:
        return False
    for word in item_words:
        if len(word) < 3:
            continue
        if token == word or token.startswith(word) or word.startswith(token):
            return True
    return False


def _is_elliptical_order(normalized: str, item_words: set[str]) -> bool:
    """An order stated as little more than the item: "zinger burger please".

    Two rules keep this narrow. Everything that is not the item, a number, a modifier or
    politeness disqualifies it, which separates "zinger burger please" from "burger
    recipe please". And the message must carry SOMETHING beyond the bare name, because a
    bare "zinger burger" is just as likely to be a price question - answering that is
    recoverable, ordering uninvited is not.

    Whatever follows a modifier is the preparation rather than the order, so "burger
    without mayo please" is read as a burger, not as a burger and some mayo.
    """
    tokens = normalized.split()
    for index, token in enumerate(tokens):
        if token in MODIFIER_HINTS:
            tokens = tokens[:index]
            break

    quantities = SPELLED_QUANTITIES | AMBIGUOUS_QUANTITIES
    has_request_marker = any(
        token in _ORDER_FILLER or token in quantities or token.isdigit() or token in MODIFIER_HINTS
        for token in normalized.split()
    )
    if not has_request_marker:
        return False

    content = [
        token
        for token in tokens
        if token not in _ORDER_FILLER and token not in quantities and not token.isdigit()
    ]
    return bool(content) and all(_word_matches_item(token, item_words) for token in content)


def _has_quantity(normalized: str, *, allow_ambiguous: bool = False, item_words: set[str] | None = None) -> bool:
    """Whether the message states a quantity to order.

    A bare number is the hard case. "2 zinger burgers" is an order; "the burger has 3
    patties", "burger under 500" and "the burger is 500 rupees" are sentences about the
    item that merely contain a digit, and reading those as quantities ordered food off
    the back of small talk.

    Two rules settle it. A number above the per-line maximum cannot be a quantity at all,
    which removes every price. Below that, the number has to look like it is counting the
    item: leading the message, or sitting next to the item's own words.
    """
    tokens = normalized.split()
    token_set = set(tokens)
    item_words = item_words or set()

    def mentions_item(candidates: set[str]) -> bool:
        """Whether any of these words names the item, allowing for plurals.

        The catalog name is "Zinger Burger" and people type "2 burgers", so an exact
        set intersection missed the most ordinary phrasing there is.
        """
        return any(_word_matches_item(word, item_words) for word in candidates)

    def counts_the_item(index: int) -> bool:
        """A number is a quantity when it leads, or sits beside the item's own words.

        "2 zinger burgers" counts. "the burger has two patties" and "i waited ten
        minutes for my burger" do not: the number is describing something else in a
        sentence that happens to mention the item.
        """
        if index == 0:
            # Leading, but the item still has to follow it: "2 zinger burgers" is an
            # order, "two of my friends hated the burger" is a sentence about people.
            return mentions_item(set(tokens[1:4]))
        neighbours = set(tokens[max(0, index - 1) : index]) | set(tokens[index + 1 : index + 2])
        return mentions_item(neighbours)

    for index, token in enumerate(tokens):
        if token.isdigit():
            # Larger than a line can hold, so it is a price, a year or an address.
            if int(token) > MAX_LINE_QUANTITY:
                continue
            if counts_the_item(index):
                return True
        elif token in SPELLED_QUANTITIES:
            # The same rule, which spelled numbers used to skip completely.
            if counts_the_item(index):
                return True

    return allow_ambiguous and bool(token_set & AMBIGUOUS_QUANTITIES)


def _is_question(message_text: str, normalized: str, *, allow_polite_bypass: bool = True) -> bool:
    """Whether this reads as a question rather than an instruction to change the cart.

    A question must never change the basket. `allow_polite_bypass` is switched off when
    the message names a destructive verb: a polite shape may rescue "can I get two
    burgers" from being read as an enquiry, but it must never rescue "can I delete a
    line" into an actual deletion. Getting an order wrong costs a correction; deleting
    somebody's cart line unasked is not something they can undo.
    """
    if _contains_phrase(normalized, HYPOTHETICAL_HINTS):
        return True
    if normalized.split(" ", 1)[0] in INFORMATIONAL_OPENERS:
        return True
    if allow_polite_bypass and _is_polite_request(normalized):
        return False
    if "?" in str(message_text or ""):
        return True
    return _contains_phrase(normalized, QUESTION_HINTS)


# Longest reply still treated as a plain "yes". Anything wordier is the customer saying
# something else that happens to start with "ok", and acting on it cleared real carts.
MAX_CONFIRMATION_TOKENS = 3


def is_affirmative(message_text: str) -> bool:
    """Whether this is a plain yes.

    Deliberately strict. A pending question is resolved by a short answer; "ok but what
    is the total first" and "ok, actually just add fries" are new requests, and reading
    either as agreement to a destructive action is exactly the mistake worth avoiding.
    """
    normalized = normalize_message_text(message_text)
    tokens = normalized.split()
    if not tokens or len(tokens) > MAX_CONFIRMATION_TOKENS:
        return False
    if _is_refusal(normalized):
        return False
    token_set = set(tokens)
    if token_set & NEGATIVE_HINTS:
        return False
    # Every word has to be part of the agreement, so "ok wait" is not a yes.
    filler = {
        "please", "pls", "sure", "hai", "hn", "yes", "ok", "it", "na", "then", "bhai",
        "yaar", "ji", "jee", "aage", "hi", "bilkul",
    }
    return bool(token_set & AFFIRMATIVE_HINTS) and all(
        token in AFFIRMATIVE_HINTS or token in filler for token in tokens
    )


def is_negative(message_text: str) -> bool:
    return bool(set(normalize_message_text(message_text).split()) & NEGATIVE_HINTS)


# Words that can sit around a "no" without turning it into a request. Politeness,
# address, and the Urdu particles that carry a refusal: "nahi bhai abhi rehne do".
_REFUSAL_FILLER = {
    "thanks", "thank", "you", "please", "plz", "pls", "it", "that", "this", "any", "more",
    "now", "for", "the", "a", "an", "i", "me", "my", "we", "us", "to", "do", "dont",
    "want", "need", "bhai", "yaar", "ji", "jee", "abhi", "ab", "aur", "koi", "kuch",
    "mujhe", "mujhay", "hai", "hy", "karo", "kar", "karna", "chahiye", "leave", "as", "is",
}


YES = "yes"
NO = "no"
UNCLEAR = "unclear"

# Ways of refusing that survive `normalize_message_text`, which strips apostrophes: "don't"
# arrives as "don t", so no token test could ever see it. These are matched against the
# normalized string and then REMOVED, and what is left decides whether the message was a
# refusal or a refusal followed by a request.
_NO_PATTERNS = (
    r"\bno\b", r"\bnope\b", r"\bnah\b", r"\bnahi+n?\b", r"\bmat\b", r"\bnai\b",
    r"\bdon t\b", r"\bdont\b", r"\bdo not\b", r"\bcan t\b", r"\bcant\b",
    r"\bcannot\b", r"\bwon t\b", r"\bwont\b", r"\bnot now\b", r"\bnever mind\b",
    r"\bnevermind\b", r"\bforget it\b", r"\bchanged my mind\b", r"\bskip it\b",
    r"\brather not\b", r"\brehne do\b", r"\brehne\b", r"\bchodo\b", r"\bnot\b",
)

# Words that can sit around a refusal without turning it into a request. Deliberately
# small, and deliberately containing no verbs of wanting: "want", "need" and "chahiye"
# were added here to let one Urdu sentence through and turned "no, I want more" into a
# bare no, discarding the request.
_REFUSAL_FILLER = {
    "thanks", "thank", "you", "please", "plz", "pls", "it", "that", "this", "now",
    "for", "the", "a", "an", "i", "me", "my", "we", "us", "to", "do", "is", "as",
    "leave", "bhai", "yaar", "ji", "jee", "abhi", "ab", "mujhe", "mujhay", "hai", "karo",
    "kar", "right", "ok", "okay",
}


def classify_confirmation_answer(message_text: str) -> str:
    """What a customer's reply means to an outstanding yes-or-no question.

    Returns YES, NO or UNCLEAR. This replaced `is_refusal_answer`, `is_mixed_answer` and
    the ad-hoc combinations of `is_affirmative`/`is_negative` that the confirmation branch
    used to make for itself. Those disagreed with one another, and the disagreements were
    where the bugs lived.

    Only YES may apply anything. NO and UNCLEAR are handled identically by the caller -
    the proposal is dropped and the customer is told - so the cost of misreading a reply
    as UNCLEAR is one repeated question, and there is no reading that silently changes a
    cart.
    """
    normalized = normalize_message_text(message_text)
    tokens = normalized.split()
    if not tokens:
        return UNCLEAR

    refusal_found = False
    stripped = normalized
    for pattern in _NO_PATTERNS:
        if re.search(pattern, stripped):
            refusal_found = True
            stripped = re.sub(pattern, " ", stripped)

    if refusal_found:
        # A message that is ONLY a refusal is a no. One that refuses and then asks for
        # something is a request, and answering it "Left your cart as it is" threw the
        # request away.
        remainder = [
            token
            for token in stripped.split()
            if token not in _REFUSAL_FILLER and token not in AFFIRMATIVE_HINTS
        ]
        return NO if not remainder else UNCLEAR

    return YES if is_affirmative(message_text) else UNCLEAR


def is_refusal_answer(message_text: str) -> bool:
    """Whether this is a NO to an outstanding question, rather than a message that
    happens to contain a negative word.

    `is_negative` is an unbounded token test and is used all over the planner, where that
    is what is wanted. Used to resolve a confirmation it swallowed whole sentences: "add
    fries but no onions" and "stop asking, just add it" were both answered "Left your cart
    as it is", and the customer's actual request was discarded with the proposal.

    An answer to a yes-or-no question is short, which is the same rule `is_affirmative`
    already applies. A longer message that is unmistakably a refusal still counts.
    """
    normalized = normalize_message_text(message_text)
    tokens = normalized.split()
    if not tokens:
        return False
    if not set(tokens) & NEGATIVE_HINTS and not _is_refusal(normalized):
        return False
    # What is LEFT once the refusal is taken out. A message that is nothing but a no is an
    # answer; one that says no and then asks for something is a request, and answering it
    # "Left your cart as it is" threw the request away. A token count cannot tell them
    # apart: "add fries no onions" and "nahi mujhe nahi chahiye" are both four words.
    remainder = [
        token
        for token in tokens
        if token not in NEGATIVE_HINTS
        and token not in AFFIRMATIVE_HINTS
        and token not in _REFUSAL_FILLER
    ]
    return not remainder


def is_mixed_answer(message_text: str) -> bool:
    """Whether the message agrees and refuses at once, like "yes, no onions".

    This is reported so the REPLY can say the answer was not understood. It must never be
    used to withhold a refusal. Treating "nahi karo" as ambiguous - which it is, by tokens,
    because `karo` is an agreement word - left a destructive proposal armed after the
    customer had plainly said no in Roman Urdu, and a later "ok" applied it.

    Refusing costs nothing and agreeing costs the cart, so a negative always wins.
    """
    tokens = set(normalize_message_text(message_text).split())
    return bool(tokens & NEGATIVE_HINTS) and bool(tokens & AFFIRMATIVE_HINTS)


def extract_bare_quantity(message_text: str) -> int | None:
    """A quantity that refers to something already in the basket, not a new item."""
    normalized = normalize_message_text(message_text)
    for pattern in BARE_QUANTITY_PATTERNS:
        match = pattern.search(normalized)
        if match:
            try:
                value = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 999:
                return value
    return None


def classify_basket_intent(message_text: str, matched_items: list[dict[str, Any]] | None = None, basket_lines: list[Any] | None = None) -> str:
    """What the customer wants done to their basket, if anything.

    Deliberately separate from ``classify_message_intent``: that one decides what to
    *say*, this one decides what to *do*. Keeping them apart means a question about
    price can never be mistaken for an instruction to change the cart.
    """
    normalized = normalize_message_text(message_text)
    if not normalized:
        return NONE

    matched_items = matched_items or []
    basket_lines = basket_lines or []

    names_destructive_verb = _contains_phrase(normalized, CLEAR_HINTS | REMOVE_HINTS)

    # ---------------------------------------------------------------- suppressors --
    #
    # Every reason NOT to act is evaluated here, once, for every intent. Earlier versions
    # attached these to individual branches - reported speech guarded removals but not
    # adds, refusal guarded destructive verbs but not adds - and each time the branch
    # that was missed became the hole. A rule that applies to one kind of cart write
    # applies to all of them, so it is checked in one place.
    all_action_hints = STRONG_ADD_HINTS | WEAK_ADD_HINTS | REMOVE_HINTS | CLEAR_HINTS | CHECKOUT_HINTS

    # "I can't order the burger", "don't add the fries". Adjacency is what decides:
    # "no onions, add a burger" is an order with a note attached, not a refusal.
    if _negates(normalized, all_action_hints):
        return NONE
    if names_destructive_verb and _is_refusal(normalized):
        return NONE

    # "My friend says add 2 burgers", "the sign says buy one burger", "usne kaha add
    # karo". The verb is being reported, not used.
    if _contains_phrase(normalized, REPORTED_SPEECH_HINTS):
        return NONE

    if _is_question(message_text, normalized, allow_polite_bypass=not names_destructive_verb):
        # Reading the cart is not a change, so "what is in my basket?" is still answered.
        # Everything below this point writes, and a question must never reach it.
        #
        # A question that also names an action ("how do I remove items from my cart?")
        # is asking how something works, not asking to see the cart, so it goes to the
        # ordinary reply path rather than dumping the basket back at them.
        # VIEW words are excluded deliberately: "cart" is in both ORDER_HINTS and
        # VIEW_HINTS, so including it here made every question about a cart return
        # nothing instead of showing the cart.
        asks_about_an_action = _contains_phrase(
            normalized,
            (CLEAR_HINTS | REMOVE_HINTS | CHECKOUT_HINTS | STRONG_ADD_HINTS) - VIEW_HINTS,
        )
        if _contains_phrase(normalized, VIEW_HINTS) and not matched_items and not asks_about_an_action:
            return VIEW
        return NONE

    # Order matters: the destructive and terminal verbs are checked before the additive
    # one, because "cancel everything" also contains order-ish words.
    if _contains_phrase(normalized, CLEAR_HINTS):
        return CLEAR
    if _contains_phrase(normalized, CHECKOUT_HINTS):
        return CHECKOUT
    if _contains_phrase(normalized, REMOVE_HINTS):
        return REMOVE

    has_bare_quantity = extract_bare_quantity(message_text) is not None
    if has_bare_quantity and basket_lines:
        return UPDATE
    if _contains_phrase(normalized, UPDATE_HINTS) and basket_lines:
        # "change the fries to 4" names a line, not a catalog item, so the basket itself
        # has to be consulted before deciding this is not an update.
        if has_bare_quantity or matched_items or score_basket_lines(message_text, basket_lines):
            return UPDATE

    # A view request only counts when nothing is being added in the same breath.
    if _contains_phrase(normalized, VIEW_HINTS) and not matched_items:
        return VIEW

    # A bare item name is deliberately not an add: "zinger burger" on its own is just as
    # likely to be a price or availability question, and adding it uninvited is worse
    # than asking. There has to be a verb or a quantity.
    # A question is never an add, however many item names or numbers it contains. Before
    # this check, "tell me more about the zinger burger" and "is the burger under 500?"
    # both wrote to a signed-in customer's cart, because "more" counted as a hint and any
    # bare number counted as a quantity.
    if matched_items:
        item_words = {
            word
            for entry in matched_items
            for word in normalize_message_text(str(entry.get("name") or "")).split()
        }

        # A polite request that names an item is as explicit as an imperative: "may I
        # have a zinger burger" asks for the burger just as plainly as "add a burger".
        # An ordering verb pointed at information is a request for information.
        asks_for_information = _contains_phrase(normalized, INFORMATION_NOUNS)
        if not asks_for_information and (
            _contains_phrase(normalized, STRONG_ADD_HINTS) or _is_polite_request(normalized)
        ):
            return ADD

        # An elliptical order: nothing in the message but the item, a quantity, a
        # modifier and politeness. "zinger burger please" and "burger without mayo
        # please" are how people actually order; "burger recipe please" names something
        # else, so it is a question.
        if _is_elliptical_order(normalized, item_words):
            return ADD

        # Otherwise a quantity is required, written as a digit or a word. Articles and
        # Urdu "do" are admitted only alongside a weak add hint, so "a burger please"
        # orders while "there was a hair in the burger" does not.
        # A quantity on its own is the weakest evidence there is, so it does not carry a
        # sentence that is negated or merely describing something. An explicit add verb
        # was already handled above and is unaffected.
        negated = bool(set(normalized.split()) & _NEGATION_TOKENS)
        describing = _contains_phrase(normalized, STATEMENT_HINTS)
        if not negated and not describing and _has_quantity(
            normalized,
            allow_ambiguous=_contains_phrase(normalized, WEAK_ADD_HINTS),
            item_words=item_words,
        ):
            return ADD

    return NONE


# ------------------------------------------------------------------- plan and action --


@dataclass(frozen=True)
class BasketAction:
    """One change to apply. ``itemId`` for adds, ``lineId`` for edits."""

    verb: str
    itemId: str = ""
    lineId: str = ""
    quantity: int = 1
    variantIndex: int | None = None
    label: str = ""
    # The plain name of what this acts on, with no verb attached. `label` is phrased as
    # something that already happened, which cannot be reused to ask a question.
    subject: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {"verb": self.verb, "quantity": self.quantity, "label": self.label}

    def storage_dict(self) -> dict[str, Any]:
        """Everything needed to replay this action on a later turn.

        Held while the customer is deciding, so that "yes" applies exactly what the
        question described and nothing that was re-derived from the word "yes".
        """
        return {
            "verb": self.verb,
            "itemId": self.itemId,
            "lineId": self.lineId,
            "quantity": self.quantity,
            "variantIndex": self.variantIndex,
            "label": self.label,
            "subject": self.subject,
        }

    @classmethod
    def from_storage(cls, data: dict[str, Any]) -> "BasketAction":
        """Rebuild a stored action, tolerating anything malformed.

        A stored confirmation can be older than the running code, so nothing here may
        raise on a shape it does not recognise.
        """
        try:
            quantity = int(data.get("quantity") or 1)
        except (TypeError, ValueError):
            quantity = 1
        variant_index = data.get("variantIndex")
        if not isinstance(variant_index, int):
            variant_index = None
        return cls(
            verb=str(data.get("verb") or ""),
            itemId=str(data.get("itemId") or ""),
            lineId=str(data.get("lineId") or ""),
            quantity=max(1, quantity),
            variantIndex=variant_index,
            label=str(data.get("label") or ""),
            subject=str(data.get("subject") or ""),
        )

    def proposal_text(self) -> str:
        """The action phrased as something not yet done, for the confirming question."""
        subject = self.subject or "that item"
        if self.verb == "add":
            return f"add {self.quantity} x {subject}"
        if self.verb == "remove":
            return f"remove {subject}"
        if self.verb == "set_quantity":
            return f"change {subject} to {self.quantity}"
        if self.verb == "clear":
            return "clear your whole cart"
        return self.label or self.verb


@dataclass(frozen=True)
class BasketPlan:
    """What the agent intends to do, and whether it may do it yet."""

    intent: str
    actions: list[BasketAction] = field(default_factory=list)
    requiresConfirmation: bool = False
    confirmationPrompt: str = ""
    # The line a pending confirmation refers to. Without it a "yes" to "should I remove
    # the fries?" cannot be told from a "yes" to anything else, which is how agreeing to
    # remove one item ended up clearing the whole cart.
    confirmationLineId: str = ""
    clarification: str = ""
    note: str = ""

    @property
    def has_actions(self) -> bool:
        return bool(self.actions)

    @property
    def needs_reply_only(self) -> bool:
        """True when the agent should talk rather than act."""
        return not self.actions and bool(self.clarification or self.confirmationPrompt or self.note)

    def public_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "actions": [action.public_dict() for action in self.actions],
            "requiresConfirmation": self.requiresConfirmation,
            "confirmationPrompt": self.confirmationPrompt,
            "clarification": self.clarification,
            "note": self.note,
        }


def _line_label(line: Any) -> str:
    name = getattr(line, "name", "") or ""
    variant = getattr(line, "selectedVariantName", "") or ""
    return f"{name} ({variant})" if variant else name


def _stem_tokens(tokens) -> set[str]:
    """Fold simple plurals so "remove the burgers" finds the "Zinger Burger" line.

    A trailing "s" is the only ending handled, which is enough for the catalog nouns
    this sees and cheap enough to stay predictable.
    """
    stemmed = set()
    for token in tokens:
        stemmed.add(token)
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            stemmed.add(token[:-1])
    return stemmed


def score_basket_lines(message_text: str, basket_lines: list[Any]) -> list[tuple[int, Any]]:
    """Rank basket lines by how well they match what the customer said, best first.

    Scores the line's own name *and* its variant, so "remove the red one" finds the
    Red / Small line even though "red" never appears in the item name.
    """
    normalized = normalize_message_text(message_text)
    if not normalized or not basket_lines:
        return []

    tokens = _stem_tokens(normalized.split())
    scored: list[tuple[int, Any]] = []
    for line in basket_lines:
        haystack = normalize_message_text(f"{getattr(line, 'name', '')} {getattr(line, 'selectedVariantName', '')}")
        line_tokens = _stem_tokens(haystack.split())
        overlap = tokens & line_tokens
        if not overlap:
            continue
        # A whole-name mention beats a single shared word such as a colour.
        score = len(overlap) * 2 + (5 if haystack and haystack in normalized else 0)
        scored.append((score, line))

    scored.sort(key=lambda row: row[0], reverse=True)
    return scored


def match_basket_lines(message_text: str, basket_lines: list[Any]) -> list[Any]:
    return [line for _, line in score_basket_lines(message_text, basket_lines)]


def _select_items_to_add(message_text: str, matched_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One item, unless the customer clearly listed several.

    Mirrors the existing draft builder: guessing at a second item from a fuzzy match is
    how a basket gains things nobody asked for.
    """
    if not matched_items:
        return []
    normalized = normalize_message_text(message_text)
    joined = any(token in normalized for token in (" and ", " aur ", ",", "+"))
    named = [item for item in matched_items if normalize_message_text(item.get("name", "")) in normalized]
    if joined and len(named) > 1:
        return named[:5]
    return matched_items[:1]


def plan_basket_actions(
    message_text: str,
    *,
    matched_items: list[dict[str, Any]] | None = None,
    basket_lines: list[Any] | None = None,
    pending_confirmation: dict[str, Any] | None = None,
) -> BasketPlan:
    """Decide what to do to the basket. Pure - nothing here writes.

    ``pending_confirmation`` carries a destructive verb the customer was asked about on
    the previous turn, so "yes" resolves it rather than being classified afresh.
    """
    matched_items = matched_items or []
    basket_lines = list(basket_lines or [])

    pending_verb = str((pending_confirmation or {}).get("verb") or "")

    # An outstanding removal question. "Yes" here means remove THAT line, and nothing
    # else: this used to be labelled as a clear, so agreeing wiped the entire cart.
    if pending_verb == REMOVE:
        if is_negative(message_text):
            return BasketPlan(intent=REMOVE, note="Left your cart as it is.")
        if is_affirmative(message_text):
            target_id = str((pending_confirmation or {}).get("lineId") or "")
            target = next((line for line in basket_lines if str(line.lineId) == target_id), None)
            if not target:
                return BasketPlan(intent=REMOVE, note="That item is no longer in your cart.")
            return BasketPlan(
                intent=REMOVE,
                actions=[BasketAction(verb="remove", lineId=target.lineId, subject=_line_label(target), label=f"Removed {_line_label(target)}")],
            )
        # Anything else is a new request; fall through and classify it afresh rather than
        # holding the customer in a loop.

    # An outstanding question takes precedence: "yes" after "clear your cart?" means
    # clear, not whatever the classifier would otherwise read into it.
    if pending_verb in {"clear", CLEAR}:
        if is_negative(message_text):
            return BasketPlan(intent=CLEAR, note="Left your cart as it is.")
        if is_affirmative(message_text):
            if not basket_lines:
                return BasketPlan(intent=CLEAR, note="Your cart is already empty.")
            return BasketPlan(
                intent=CLEAR,
                actions=[BasketAction(verb="clear", label="Cleared the cart")],
            )
        return BasketPlan(
            intent=CLEAR,
            requiresConfirmation=True,
            confirmationPrompt="Just to confirm - should I clear your cart? Reply yes or no.",
        )

    intent = classify_basket_intent(message_text, matched_items, basket_lines)

    if intent == CLEAR:
        if not basket_lines:
            return BasketPlan(intent=CLEAR, note="Your cart is already empty.")
        # Destructive, so it is always asked before it is done. The action travels with
        # the question: a "yes" replays exactly this, rather than being re-classified
        # from the word "yes" against whatever the cart looks like by then.
        return BasketPlan(
            intent=CLEAR,
            actions=[BasketAction(verb="clear", label="Cleared the cart")],
            requiresConfirmation=True,
            confirmationPrompt=f"Are you sure you want to clear your cart? That removes all {len(basket_lines)} item(s).",
        )

    if intent == REMOVE:
        if not basket_lines:
            return BasketPlan(intent=REMOVE, note="There is nothing in your cart to remove.")
        # Removing a line cannot be undone by the customer, so it is applied only when it
        # was actually asked for as an order. Anything else - a hedge, a musing, a
        # question the classifier let through - is confirmed first. This is what stops
        # the guards above from having to be exhaustive to be safe.
        scored = score_basket_lines(message_text, basket_lines)
        if not _is_direct_instruction(normalize_message_text(message_text), REMOVE_HINTS):
            # Name the line, so agreeing is agreeing to something specific.
            if len(scored) == 1 or (len(scored) > 1 and scored[0][0] > scored[1][0]):
                target = scored[0][1]
                return BasketPlan(
                    intent=REMOVE,
                    actions=[
                        BasketAction(
                            verb="remove",
                            lineId=target.lineId,
                            subject=_line_label(target),
                            label=f"Removed {_line_label(target)}",
                        )
                    ],
                    requiresConfirmation=True,
                    confirmationLineId=str(target.lineId),
                    confirmationPrompt=f"Just to confirm - should I remove {_line_label(target)} from your cart? Reply yes or no.",
                )
            return BasketPlan(
                intent=REMOVE,
                clarification="Which item should I remove? " + ", ".join(_line_label(line) for line in basket_lines[:5]),
            )
        if not scored:
            # A one-item cart used to be deleted whenever nothing matched, on the theory
            # that there was only one thing it could mean. That made every
            # misclassification an unconfirmed, unrecoverable deletion. It is only safe
            # when the customer pointed at the line - "remove it", or a bare "remove".
            if len(basket_lines) == 1 and _refers_to_the_only_line(normalize_message_text(message_text)):
                target = basket_lines[0]
                return BasketPlan(
                    intent=REMOVE,
                    actions=[BasketAction(verb="remove", lineId=target.lineId, subject=_line_label(target), label=f"Removed {_line_label(target)}")],
                )
            return BasketPlan(
                intent=REMOVE,
                clarification="Which item should I remove? " + ", ".join(_line_label(line) for line in basket_lines[:5]),
            )
        # Two lines matching equally well is a real ambiguity - "remove the shirt" with a
        # blue and a red shirt in the cart. Removing the wrong one is not something the
        # customer can undo without noticing first, so ask instead.
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            tied = [line for score, line in scored if score == scored[0][0]]
            return BasketPlan(
                intent=REMOVE,
                clarification="Which one did you mean? " + ", ".join(_line_label(line) for line in tied[:3]),
            )
        target = scored[0][1]
        return BasketPlan(
            intent=REMOVE,
            actions=[BasketAction(verb="remove", lineId=target.lineId, subject=_line_label(target), label=f"Removed {_line_label(target)}")],
        )

    if intent == UPDATE:
        if not basket_lines:
            return BasketPlan(intent=UPDATE, note="There is nothing in your cart to change yet.")
        quantity = extract_bare_quantity(message_text)
        scored = score_basket_lines(message_text, basket_lines)
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            tied = [line for score, line in scored if score == scored[0][0]]
            return BasketPlan(
                intent=UPDATE,
                clarification="Which one did you mean? " + ", ".join(_line_label(line) for line in tied[:3]),
            )
        target = scored[0][1] if scored else (basket_lines[0] if len(basket_lines) == 1 else None)

        if target is None:
            return BasketPlan(
                intent=UPDATE,
                clarification="Which item's quantity should I change? " + ", ".join(_line_label(line) for line in basket_lines[:5]),
            )
        if quantity is None:
            # extract_quantity always answers, defaulting to 1, so the None-able helper is
            # the one to use here: "change the shirt" with no number is a question, not an
            # instruction to set the quantity to 1.
            quantity = extract_numeric_quantity(message_text)
        if quantity is None:
            return BasketPlan(intent=UPDATE, clarification=f"How many {_line_label(target)} would you like?")
        if quantity <= 0:
            return BasketPlan(
                intent=UPDATE,
                actions=[BasketAction(verb="remove", lineId=target.lineId, subject=_line_label(target), label=f"Removed {_line_label(target)}")],
            )
        return BasketPlan(
            intent=UPDATE,
            actions=[
                BasketAction(
                    verb="set_quantity",
                    lineId=target.lineId,
                    quantity=quantity,
                    subject=_line_label(target),
                    label=f"Set {_line_label(target)} to {quantity}",
                )
            ],
        )

    if intent == ADD:
        selected = _select_items_to_add(message_text, matched_items)
        if not selected:
            return BasketPlan(intent=ADD, clarification="Which item would you like me to add?")
        actions = []
        for item in selected:
            quantity = extract_quantity(message_text, item.get("name", ""))
            variant = item.get("agentMatchedVariant") or None
            variant_index = variant.get("variantIndex") if variant else None
            label_name = item.get("name", "item")
            if variant and variant.get("name"):
                label_name = f"{label_name} ({variant['name']})"
            actions.append(
                BasketAction(
                    verb="add",
                    itemId=str(item.get("_id", item.get("id", ""))),
                    quantity=quantity,
                    variantIndex=variant_index,
                    subject=label_name,
                    label=f"Added {quantity} x {label_name}",
                )
            )
        return BasketPlan(intent=ADD, actions=actions)

    if intent == VIEW:
        return BasketPlan(intent=VIEW)

    if intent == CHECKOUT:
        if not basket_lines:
            return BasketPlan(intent=CHECKOUT, note="Your cart is empty, so there is nothing to check out yet.")
        return BasketPlan(intent=CHECKOUT)

    return BasketPlan(intent=NONE)


# ------------------------------------------------------------------- readiness --


def checkout_readiness(
    basket_summary: dict[str, Any],
    checkout_draft: dict[str, Any] | None = None,
    *,
    has_account: bool = True,
    allowed_fulfillment_types: list[str] | None = None,
) -> dict[str, Any]:
    """What still has to be decided before this basket can become an order.

    The chat panel used to compute this in React and the cart page computed it again,
    which is two places for the rules to drift apart. Now the server answers once and
    both surfaces render what it says.

    A guest has no profile to draw a name and phone from, so those are only required
    when there is no account behind the basket.
    """
    draft = checkout_draft or {}
    missing: list[str] = []
    # The same list in field names. The sentences are for the customer; these are what
    # gates the free-text harvester, which may only record an answer to a question that
    # was actually asked.
    missing_fields: list[str] = []

    if basket_summary.get("isEmpty", True):
        missing.append("Add at least one item to your cart.")
        # `missingFields` gates what the free-text harvester may record, and an empty cart
        # is not a checkout in progress. Reporting both fields as outstanding here held
        # the gate open from the first message of every conversation, which is most of
        # why it was not stopping anything.
        return {
            "canCheckout": False,
            "missing": missing,
            "missingFields": [],
            "itemCount": basket_summary.get("itemCount", 0),
            "subtotal": basket_summary.get("subtotal", 0),
            "currency": basket_summary.get("currency", "PKR"),
        }

    fulfillment = str(draft.get("fulfillmentType") or "").strip()
    allowed = allowed_fulfillment_types or ["none", "pickup", "delivery"]
    # "none" means the business does not deliver or offer pickup, so there is nothing to
    # ask: only prompt when the customer actually has a choice to make.
    if not fulfillment and [option for option in allowed if option != "none"]:
        missing.append("Choose pickup or delivery.")
        missing_fields.append("fulfillmentType")
    if fulfillment == "delivery":
        if not str(draft.get("addressLine1") or "").strip():
            missing.append("Add your delivery address.")
            missing_fields.append("addressLine1")
        if not str(draft.get("addressCity") or "").strip():
            missing.append("Add your city.")
            missing_fields.append("addressCity")

    if not str(draft.get("paymentMethod") or "").strip():
        missing.append("Choose a payment method.")
        missing_fields.append("paymentMethod")

    if not has_account:
        if not str(draft.get("customerName") or "").strip():
            missing.append("Tell me your name.")
            missing_fields.append("customerName")
        if not str(draft.get("customerPhone") or "").strip():
            missing.append("Tell me your phone number.")
            missing_fields.append("customerPhone")

    return {
        "canCheckout": not missing,
        "missing": missing,
        "missingFields": missing_fields,
        "itemCount": basket_summary.get("itemCount", 0),
        "subtotal": basket_summary.get("subtotal", 0),
        "currency": basket_summary.get("currency", "PKR"),
    }


def _matches_whole_phrase(phrase: str, normalized: str) -> bool:
    """Match a phrase on word boundaries.

    Needed because "jazzcash" contains "cash": a plain substring check read
    "pay with jazzcash" as cash on delivery.
    """
    return re.search(r"\b" + re.escape(phrase) + r"\b", normalized) is not None


# Things a customer says that set a checkout field rather than changing the basket.
# A checkout detail is only recorded when the customer is choosing, not merely using
# the word. Without this, "the delivery guy was rude" set the fulfilment type and "my
# bank is closed today" set the payment method.
# A narrower set: the customer speaking about their OWN intention, right now. This is what
# it takes to CHANGE a choice that is already recorded, as opposed to filling an empty
# one. "paid by", "please" and "use" are deliberately absent, because "my friend paid by
# jazzcash last time" must not overwrite a payment method the customer already gave.
REVISION_HINTS = {
    "i want", "i will", "i ll", "ill", "i d", "id like", "i would", "make it", "lets",
    "let us", "prefer", "choose", "select", "set it", "actually", "instead", "change it",
    "change to", "change it to", "switch", "switch to", "rather", "ill pay", "i pay",
    "karo", "kardo", "kar do", "karunga", "karungi", "chahiye",
}

# Whole phrases, longest first when they are stripped, so that "bhej do" is removed as a
# unit. Listing only "bhej" detected the choice but left "do" behind, and a leftover word
# is what tells a remark from an answer.
PAYMENT_PHRASES = {
    # Order matters: the named wallets are checked first, and "cash" is matched as a whole
    # word, because "jazzcash" contains "cash" and a substring check once read "pay with
    # jazzcash" as cash on delivery.
    "jazzcash": ("jazzcash", "jazz cash"),
    "easypaisa": ("easypaisa", "easy paisa"),
    "manual_bank": ("bank transfer", "bank"),
    "cod": ("cash on delivery", "cod", "cash"),
}

FULFILLMENT_PHRASES = {
    "delivery": (
        "deliver", "delivered", "delivery", "home", "house", "ghar", "bhej do", "bhej",
        "bhejo",
    ),
    "pickup": ("pickup", "pick up", "collect", "self", "khud", "ajaunga", "aunga", "le lunga"),
}


# Words that carry no meaning of their own in a short reply, so leaving them behind does
# not make a message into a sentence. Deliberately contains no verbs: "is", "was" and
# "hai" are exactly what separates "delivery" from "delivery was late".
# Everything that can WRAP an answer without adding anything to it: politeness, the
# first person, and the verbs of asking. If a message contains a word that is not here and
# is not the choice itself, it is a sentence about the choice rather than an answer to a
# question about it - "delivery" against "delivery was late", "i want to have it delivered"
# against "i want my delivery refunded".
#
# This is the ONLY list the extractor consults, which is the point. It replaced request
# hints, payment hints, a connective set and a token-distance window, four lists that were
# tuned against the same few dozen sentences for seven rounds and contradicted each other
# by the end of it.
_ANSWER_FILLER = {
    # politeness and acknowledgement
    "please", "plz", "pls", "ok", "okay", "then", "actually", "instead",
    # the first person, and the second
    "i", "ill", "id", "im", "me", "my", "myself", "we", "us", "our", "ourselves",
    "you", "your",
    # verbs of asking, choosing and receiving
    "want", "will", "would", "like", "take", "have", "get", "do", "make", "made",
    "send", "pay", "use", "using", "choose", "select", "prefer", "set", "change",
    "switch", "lets", "let", "go", "put", "need", "needs", "give",
    # articles, prepositions, particles
    "it", "the", "a", "an", "to", "for", "with", "through", "by", "on", "in", "and",
    "some", "is", "be", "this", "that",
    # Roman Urdu equivalents
    "kar", "karo", "kardo", "karna", "karunga", "karungi", "krna", "chahiye", "chaiye",
    "mujhe", "mujhay", "ji", "jee", "han", "haan", "bhi", "wala", "walay", "wali",
    "kr", "krdo", "dena", "dedo",
}


def _all_choice_phrases() -> tuple[str, ...]:
    """Every phrase that names a checkout choice, of any kind.

    The residue test strips all of them, not only the ones for the field being decided.
    Stripping one field's phrases left the other field's words lying there, so "deliver
    it, cash on delivery" recorded neither: each loop saw the other's answer as a leftover
    word and read the message as a sentence about the choice rather than an answer.
    """
    phrases: list[str] = []
    for group in FULFILLMENT_PHRASES.values():
        phrases.extend(group)
    for group in PAYMENT_PHRASES.values():
        phrases.extend(group)
    return tuple(phrases)


def _is_bare_answer(normalized: str, phrases: tuple[str, ...] | set[str] = ()) -> bool:
    """True when the message says nothing beyond the choice it names.

    This is the whole test now. It replaced a word count, then a hint search, then a
    token-distance window, each of which was wrong in both directions at once: the window
    could not tell "i would LIKE delivery" from "i want TO COMPLAIN ABOUT delivery",
    because both gaps are three tokens.

    What actually distinguishes an answer is that there is nothing else in it. Remove the
    phrase that matched and the words that can wrap an answer, and a real answer is empty
    while a sentence about the choice still has its own words left over.
    """
    remainder = normalized
    for phrase in sorted(set(phrases) | set(_all_choice_phrases()), key=len, reverse=True):
        remainder = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", remainder)
    return not [word for word in remainder.split() if word not in _ANSWER_FILLER]


def extract_checkout_details(
    message_text: str,
    *,
    allowed_fields: set[str] | None = None,
    revisable_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Pick up checkout details the customer mentions in passing.

    Only unambiguous signals: a guessed address is worse than an asked-for one.

    ``allowed_fields`` is the structural half of the guard, and the orchestrator always
    passes it. The word tests below decide whether a sentence LOOKS like a choice, and
    six rounds of evidence say they will keep being wrong about that; this decides
    whether the agent is even entitled to the answer, by restricting the harvest to
    fields readiness is currently asking the customer to supply. So "the delivery guy
    was rude" cannot set a fulfilment type unless the agent had just asked which one the
    customer wanted, and even then the sentence tests still have to pass.

``revisable_fields`` is the fields that already HAVE an answer. They are never in
    `allowed_fields`, and gating on that list alone made every recorded choice permanent:
    "actually jazzcash" was discarded without a word. They are a separate set rather than
    the same hole, because an empty `allowed_fields` means two opposite things - nothing
    asked yet, and everything answered already - and letting a first answer through the
    revision door reopened the original bug on the first message of every conversation.

    Changing an answer takes a customer stating their own intention (`REVISION_HINTS`) or
    a reply that is nothing but the new choice. Filling an EMPTY field from a passing
    remark is the bug; deliberately changing an answer is the customer's business.

    Passing ``None`` for both keeps the unrestricted behaviour, for callers parsing a
    message that is known to be an answer.
    """
    normalized = normalize_message_text(message_text)
    details: dict[str, Any] = {}
    if not normalized:
        return details

    # A question is not an instruction. "do you accept cash?" used to set the payment
    # method to cash on delivery, after which readiness reported the order ready to
    # place. The same goes for "do you deliver?".
    #
    # The polite bypass is switched OFF here. It exists so "can I get two burgers" is
    # read as an order, which is a safe thing to get slightly wrong; "can I get cash on
    # delivery?" is a question about what the shop accepts, and silently recording it as
    # the customer's choice is not. These details are merged into the stored checkout
    # draft, and readiness then reports the order ready to place.
    if _is_question(message_text, normalized, allow_polite_bypass=False):
        return details

    # A refusal states what the customer does NOT want. "I don't have cash" and "don't
    # deliver it, I'll pick it up" were both setting the very option being ruled out.
    if _is_refusal(normalized):
        return details

    # These have to be stated as a choice, not merely mentioned. "The delivery guy was
    # rude" and "my bank is closed today" name the words without choosing anything, so a
    # bare noun is not enough on its own.
    #
    # Either the message asks for the thing in so many words, or it consists of nothing
    # BUT the thing - which is what a reply to a direct question looks like. The second
    # test used to be a word count, and counting words cannot tell "delivery" from
    # "delivery was late". `_is_bare_answer` is checked per phrase set, below, because it
    # depends on which phrase actually matched.
    # The only thing left that a word list decides: whether an ALREADY ANSWERED field may
    # be overwritten. Filling an empty field is the dangerous direction and is governed by
    # the test below; changing an answer the customer already gave is their business, and
    # takes them saying so.
    revises = _contains_phrase(normalized, REVISION_HINTS)

    def may_write(field: str, phrases) -> bool:
        """Whether this message is entitled to set `field`."""
        if allowed_fields is None and revisable_fields is None:
            return True
        if field in (allowed_fields or set()):
            # The agent asked for this. An answer is expected.
            return True
        if field in (revisable_fields or set()):
            # It already has an answer. Changing it takes more than mentioning it.
            return revises or _is_bare_answer(normalized, phrases)
        # Neither asked for nor already answered: nothing here is the customer's choice.
        return False

    # Word boundaries, like the payment phrases below. Substring matching made "home"
    # match "homemade", "self" match "yourself" and "collect" match "collection".
    for fulfillment_type, phrases in FULFILLMENT_PHRASES.items():
        if any(_matches_whole_phrase(phrase, normalized) for phrase in phrases):
            if _negates(normalized, set(phrases)):
                continue
            if not _is_bare_answer(normalized, phrases):
                continue
            if not may_write("fulfillmentType", phrases):
                continue
            details["fulfillmentType"] = fulfillment_type
            break

    # The named wallets are checked first, and "cash" is matched as a whole word:
    # "jazzcash" contains "cash", so a substring check read "pay with jazzcash" as cash
    # on delivery.
    for method, phrases in PAYMENT_PHRASES.items():
        if any(_matches_whole_phrase(phrase, normalized) for phrase in phrases):
            if _negates(normalized, set(phrases)):
                continue
            if not _is_bare_answer(normalized, phrases):
                continue
            if not may_write("paymentMethod", phrases):
                continue
            details["paymentMethod"] = method
            break

    return details


# ------------------------------------------------------------------------ execution --


@dataclass
class ExecutionResult:
    applied: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    blocked: str = ""

    @property
    def changed(self) -> bool:
        return bool(self.applied)

    def public_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "rejected": self.rejected,
            "blocked": self.blocked,
            "changed": self.changed,
        }


async def execute_basket_actions(
    basket,
    plan: BasketPlan,
    *,
    tenant_id,
    allowed_item_ids: set[str] | None = None,
    confirmed: bool = False,
) -> ExecutionResult:
    """Apply a plan, re-checking everything it asks for.

    ``allowed_item_ids`` is the guard that makes a planner bug harmless: only items the
    catalog search surfaced this turn, or already in the basket, may be added. It is
    checked here rather than trusted from the planner, so swapping in an LLM planner
    later does not widen what can be written.
    """
    from bson import ObjectId

    from app.db.mongodb import get_database

    result = ExecutionResult()

    if plan.requiresConfirmation and not confirmed:
        result.blocked = "awaiting_confirmation"
        return result
    if not plan.actions:
        return result

    allowed_item_ids = allowed_item_ids if allowed_item_ids is not None else set()
    # Only "add" consults the catalog. Opening a connection up front made clearing or
    # removing a line depend on the database for no reason.
    db = None

    for action in plan.actions:
        try:
            if action.verb == "clear":
                removed = await basket.clear()
                result.applied.append({"verb": "clear", "label": f"Cleared {removed} item(s)", "quantity": removed})
                continue

            if action.verb == "remove":
                removed_line = await basket.remove(action.lineId)
                if removed_line is None:
                    result.rejected.append({"verb": "remove", "reason": "That item is no longer in your cart."})
                    continue
                result.applied.append({"verb": "remove", "label": action.label, "quantity": removed_line.quantity})
                continue

            if action.verb == "set_quantity":
                updated = await basket.set_quantity(action.lineId, action.quantity)
                if updated is None:
                    result.rejected.append({"verb": "set_quantity", "reason": "That item is no longer in your cart."})
                    continue
                result.applied.append({"verb": "set_quantity", "label": action.label, "quantity": updated.quantity})
                continue

            if action.verb == "add":
                if action.itemId not in allowed_item_ids:
                    # The planner named something this turn's search did not surface.
                    logger.warning("Refusing basket add for unsolicited item id %s.", action.itemId)
                    result.rejected.append({"verb": "add", "reason": "I could not find that item in this business's catalog."})
                    continue
                if not ObjectId.is_valid(action.itemId):
                    result.rejected.append({"verb": "add", "reason": "I could not find that item."})
                    continue
                if db is None:
                    db = get_database()
                item = await db.items.find_one(
                    {
                        "_id": ObjectId(action.itemId),
                        "tenantId": tenant_id,
                        "status": "active",
                        "$or": [{"isSellable": True}, {"isBookable": True}],
                    }
                )
                if not item:
                    result.rejected.append({"verb": "add", "reason": "That item is not available right now."})
                    continue
                line = await basket.add(item, action.quantity, variant_index=action.variantIndex)
                result.applied.append({"verb": "add", "label": action.label, "quantity": line.quantity})
                continue

            result.rejected.append({"verb": action.verb, "reason": "Unsupported basket action."})
        except ValueError as exc:
            result.rejected.append({"verb": action.verb, "reason": str(exc)})
        except Exception as exc:  # a bad line must not take the whole reply down
            logger.exception("Basket action %s failed: %s", action.verb, exc)
            result.rejected.append({"verb": action.verb, "reason": "That change could not be applied."})

    return result


def describe_execution(result: ExecutionResult, plan: BasketPlan) -> str:
    """One line the agent can say about what it just did."""
    if result.blocked == "awaiting_confirmation":
        return plan.confirmationPrompt
    parts = [row["label"] for row in result.applied if row.get("label")]
    if result.rejected:
        parts.extend(row["reason"] for row in result.rejected if row.get("reason"))
    return " ".join(parts).strip()
