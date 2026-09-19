"""Per-route request throttling.

The previous limiter applied one global per-IP budget to every endpoint, which meant
the only safe setting was "off": tightening it enough to protect the anonymous AI
endpoint would also throttle a signed-in owner clicking around the dashboard. Limits
are therefore declared per route group, so the expensive and abusable routes can be
strict while ordinary traffic stays generous.

Counting is split deliberately:

* Sensitive groups count in MongoDB, so the budget holds across uvicorn workers and
  survives a restart. That costs one atomic update per request, which is acceptable
  on routes that are about to call an LLM or create an order.
* The default group counts in process memory. It exists to stop a runaway client, not
  to be exact, and paying a database round trip on every dashboard request to enforce
  a 300/minute ceiling would be a poor trade.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque

from app.core.config import settings
from app.db.mongodb import get_database

RATE_LIMIT_COLLECTION = "rate_limit_counters"


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    max_requests: int
    window_seconds: int
    shared: bool = False
    methods: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
    pattern: re.Pattern | None = None

    def matches(self, method: str, path: str) -> bool:
        if method.upper() not in self.methods:
            return False
        return self.pattern is None or bool(self.pattern.search(path))


# Ordered; the first match wins. DEFAULT_RULE applies when nothing else does.
RATE_LIMIT_RULES: tuple[RateLimitRule, ...] = (
    # Each call reaches an LLM on the business's own API budget, with no account behind it.
    RateLimitRule(
        name="public_ai_chat",
        max_requests=8,
        window_seconds=60,
        shared=True,
        methods=frozenset({"POST"}),
        pattern=re.compile(r"/public/businesses/[^/]+/chat/messages$"),
    ),
    # Anonymous order creation: no login, no captcha, writes real transactions.
    RateLimitRule(
        name="public_order",
        max_requests=5,
        window_seconds=60,
        shared=True,
        methods=frozenset({"POST"}),
        pattern=re.compile(r"/public/businesses/[^/]+/(orders|transactions)$"),
    ),
    # Credential endpoints, to make online guessing impractical.
    RateLimitRule(
        name="auth_attempt",
        max_requests=10,
        window_seconds=60,
        shared=True,
        methods=frozenset({"POST"}),
        pattern=re.compile(r"/(auth/login|auth/register|auth/password|auth/otp)"),
    ),
    # Starting, verifying or resending a payment code. The challenge's own attempt
    # counter is the real control; this stops a script from burning through codes.
    RateLimitRule(
        name="payment_otp",
        max_requests=12,
        window_seconds=60,
        shared=True,
        methods=frozenset({"POST"}),
        pattern=re.compile(r"/customer/transactions/[^/]+/wallet-checkout"),
    ),
    # Signed-in chat still costs money, but the account is traceable.
    RateLimitRule(
        name="customer_ai_chat",
        max_requests=20,
        window_seconds=60,
        shared=True,
        methods=frozenset({"POST"}),
        pattern=re.compile(r"/customer/businesses/[^/]+/chat/messages$"),
    ),
)

# Generous on purpose: a dashboard page fans out into many parallel requests, and
# several staff can share one office IP.
# Honours RATE_LIMIT_REQUESTS_PER_MINUTE, which was previously defined in settings and
# read by nothing at all.
DEFAULT_RULE = RateLimitRule(
    name="default",
    max_requests=max(1, int(settings.rate_limit_requests_per_minute or 300)),
    window_seconds=60,
    shared=False,
)


def resolve_rule(method: str, path: str) -> RateLimitRule:
    for rule in RATE_LIMIT_RULES:
        if rule.matches(method, path):
            return rule
    return DEFAULT_RULE


class InMemoryWindow:
    """Best-effort sliding window for the default rule. Per process by design."""

    # How often to sweep empty buckets, in calls. Sweeping on every request would walk
    # the whole dict each time for no benefit.
    PRUNE_EVERY = 1000

    def __init__(self) -> None:
        self._hits: dict[str, Deque[float]] = defaultdict(deque)
        self._since_prune = 0
        # The window most recently used, so the sweep can tell which buckets have expired
        # rather than only removing ones that happen to be empty already.
        self._window_seconds = 60

    def hit(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        self._window_seconds = window_seconds
        bucket = self._hits[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

        if len(bucket) >= max_requests:
            self._maybe_prune()
            return False, int(window_seconds - (now - bucket[0])) + 1
        bucket.append(now)
        # Sweep only after the append. Pruning first could delete the bucket this call
        # just created through the defaultdict, and the append would then land on a
        # deque no longer in the dict, losing the hit.
        self._maybe_prune()
        return True, 0

    def _maybe_prune(self) -> None:
        self._since_prune += 1
        if self._since_prune >= self.PRUNE_EVERY:
            self._since_prune = 0
            self.prune()

    def prune(self) -> None:
        """Drop buckets that are empty OR fully expired.

        Dropping only the already-empty ones was half a fix: a bucket is emptied by the
        expiry loop in `hit`, which runs only when that same key is seen again. A client
        that makes one request and never returns kept its entry for the lifetime of the
        process, which is exactly the growth this is meant to stop.

        defaultdict keeps an entry forever once touched, so memory grew with the number
        of distinct client addresses seen over the process lifetime.
        """
        now = time.monotonic()
        cutoff = self._window_seconds
        stale = [
            existing
            for existing, bucket in self._hits.items()
            if not bucket or now - bucket[-1] > cutoff
        ]
        for stale_key in stale:
            del self._hits[stale_key]

    def reset(self) -> None:
        self._hits.clear()
        self._since_prune = 0


in_memory_window = InMemoryWindow()


def _window_start(window_seconds: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    epoch_seconds = int(now.timestamp())
    return datetime.fromtimestamp(epoch_seconds - (epoch_seconds % window_seconds), tz=timezone.utc)


async def hit_shared_window(key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
    """Fixed-window counter in MongoDB, shared by every worker.

    A fixed window can allow up to twice the budget across a boundary. That is an
    accepted trade for an atomic single-round-trip check; the alternative needs either
    a Lua-style script or a second collection, and these windows are short.
    """
    started_at = _window_start(window_seconds)
    document_id = f"{key}|{started_at.isoformat()}"
    expires_at = started_at + timedelta(seconds=window_seconds * 2)

    result = await get_database()[RATE_LIMIT_COLLECTION].find_one_and_update(
        {"_id": document_id},
        {"$inc": {"count": 1}, "$setOnInsert": {"expiresAt": expires_at}},
        upsert=True,
        return_document=True,
    )
    count = int((result or {}).get("count", 1))
    if count > max_requests:
        retry_after = int((started_at + timedelta(seconds=window_seconds) - datetime.now(timezone.utc)).total_seconds())
        return False, max(retry_after, 1)
    return True, 0


async def check_rate_limit(rule: RateLimitRule, identity: str) -> tuple[bool, int]:
    key = f"{rule.name}:{identity}"
    if rule.shared:
        try:
            return await hit_shared_window(key, rule.max_requests, rule.window_seconds)
        except Exception:
            # A limiter must never take the API down with it; fall back to local counting.
            return in_memory_window.hit(key, rule.max_requests, rule.window_seconds)
    return in_memory_window.hit(key, rule.max_requests, rule.window_seconds)
