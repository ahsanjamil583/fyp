"""One basket interface over the two places a pre-checkout order can live.

The agent must behave the same on the website and on WhatsApp, but only one of those
has an account behind it:

``CartBasket``
    Backed by the ``carts`` collection, keyed by ``(customerUserId, tenantId)``. This is
    the same cart the customer sees on the cart page, so the chat and the page can never
    disagree.
``DraftBasket``
    Backed by ``conversations.basketDraft``. Used when there is no account to attach a
    cart to - an anonymous website visitor, or a WhatsApp number that has never signed
    up. A WhatsApp-only customer can still fill a basket and order without ever creating
    a website account.

Which one answers is decided by :func:`resolve_basket`, not by the caller, so no code
path can accidentally read one customer's cart while writing another's draft.

Line identity, variant handling and pricing are deliberately shared with the HTTP cart
(``customer_portal_service``) rather than reimplemented: one definition of "the same
line", one place where a variant is validated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from bson import ObjectId

from app.core.config import settings
from app.db.mongodb import get_database
from app.core.cart_lines import (
    build_cart_line,
    cart_line_key,
    cart_line_unit_price,
    find_cart_line,
)
from app.services.localization_service import normalize_optional_pk_phone_or_blank

logger = logging.getLogger(__name__)

MAX_BASKET_LINES = 40
# Imported rather than redefined: a second copy of this number is how the cashier
# schema came to advertise 999 while the order builder refused anything over 99.
from app.services.smart_order_service import MAX_LINE_QUANTITY  # noqa: E402

LINKED_BY_SESSION = "session"
LINKED_BY_PHONE = "phone"
LINKED_BY_NONE = "none"


# What still has to be decided before an order can be placed. Held next to the basket so
# the agent can read and set it, and so it survives a page refresh - previously all of
# this lived in React state and was lost on reload.
CHECKOUT_DRAFT_FIELDS = (
    "fulfillmentType",
    "addressLine1",
    "addressCity",
    "paymentMethod",
    "notes",
    "customerName",
    "customerPhone",
    "customerEmail",
)

ALLOWED_FULFILLMENT_TYPES = {"none", "pickup", "delivery"}


def empty_checkout_draft() -> dict[str, Any]:
    return {field: "" for field in CHECKOUT_DRAFT_FIELDS}


def normalize_checkout_draft(values: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only the known fields, as trimmed strings."""
    source = values or {}
    draft = empty_checkout_draft()
    for field in CHECKOUT_DRAFT_FIELDS:
        raw = source.get(field, "")
        draft[field] = str(raw or "").strip()[:200]
    if draft["fulfillmentType"] and draft["fulfillmentType"] not in ALLOWED_FULFILLMENT_TYPES:
        draft["fulfillmentType"] = ""
    return draft


@dataclass(frozen=True)
class BasketLine:
    """One pre-checkout line, in the shape both backends agree on."""

    lineId: str
    itemId: str
    name: str
    quantity: int
    unitPrice: float
    currency: str
    subtotal: float
    selectedVariantIndex: int | None = None
    selectedVariantName: str = ""
    selectedOptions: dict[str, Any] = field(default_factory=dict)
    variantSku: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {
            "lineId": self.lineId,
            "itemId": self.itemId,
            "name": self.name,
            "quantity": self.quantity,
            "unitPrice": self.unitPrice,
            "currency": self.currency,
            "subtotal": self.subtotal,
            "selectedVariantIndex": self.selectedVariantIndex,
            "selectedVariantName": self.selectedVariantName,
            "selectedOptions": dict(self.selectedOptions),
            "variantSku": self.variantSku,
        }


@dataclass(frozen=True)
class BasketIdentity:
    """Who this basket belongs to, and how that was decided.

    ``linkedBy`` is surfaced so the agent can say "I found your account" rather than
    silently acting on a cart the customer did not expect it to reach.
    """

    channel: str
    tenantId: str
    kind: str
    customerUserId: str = ""
    conversationId: str = ""
    phone: str = ""
    linkedBy: str = LINKED_BY_NONE

    def public_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "kind": self.kind,
            "linkedBy": self.linkedBy,
            "hasAccount": bool(self.customerUserId),
        }


def _line_from_document(line: dict[str, Any], item: dict[str, Any] | None) -> BasketLine:
    quantity = int(line.get("quantity", 1) or 1)
    unit_price = cart_line_unit_price(item, line)
    return BasketLine(
        lineId=str(line.get("lineId") or line.get("itemId")),
        itemId=str(line.get("itemId")),
        name=(item or {}).get("name", "Unavailable"),
        quantity=quantity,
        unitPrice=unit_price,
        currency=(item or {}).get("currency", "PKR"),
        subtotal=round(unit_price * quantity, 2),
        selectedVariantIndex=line.get("selectedVariantIndex"),
        selectedVariantName=line.get("selectedVariantName", ""),
        selectedOptions=line.get("selectedOptions") or {},
        variantSku=line.get("variantSku", ""),
    )


class _AddRequest:
    """Adapter so ``build_cart_line`` can be reused without an HTTP payload."""

    def __init__(self, quantity: int, variant_index: int | None = None, variant_sku: str = "", options: dict | None = None):
        self.quantity = quantity
        self.selectedVariantIndex = variant_index
        self.selectedVariantName = ""
        self.selectedOptions = options or {}
        self.variantSku = variant_sku


@runtime_checkable
class ConversationBasket(Protocol):
    """What the agent may do to a basket before checkout."""

    kind: str
    identity: BasketIdentity

    async def lines(self) -> list[BasketLine]: ...
    async def add(self, item: dict[str, Any], quantity: int, variant_index: int | None = None) -> BasketLine: ...
    async def set_quantity(self, line_ref: str, quantity: int) -> BasketLine | None: ...
    async def remove(self, line_ref: str) -> BasketLine | None: ...
    async def clear(self) -> int: ...
    async def summary(self) -> dict[str, Any]: ...
    async def get_checkout_draft(self) -> dict[str, Any]: ...
    async def set_checkout_draft(self, values: dict[str, Any]) -> dict[str, Any]: ...


class _BaseBasket:
    """Behaviour shared by both backends: limits, pricing, and the summary shape."""

    kind = "base"

    def __init__(self, tenant: dict[str, Any], identity: BasketIdentity) -> None:
        self.tenant = tenant
        self.tenantId: ObjectId = tenant["_id"]
        self.identity = identity

    async def _stored_lines(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def _write_lines(self, lines: list[dict[str, Any]]) -> None:
        raise NotImplementedError

    async def _item_map(self, lines: list[dict[str, Any]]) -> dict[ObjectId, dict[str, Any]]:
        db = get_database()
        ids = [line["itemId"] for line in lines if line.get("itemId")]
        if not ids:
            return {}
        return {item["_id"]: item async for item in db.items.find({"_id": {"$in": ids}, "tenantId": self.tenantId})}

    async def lines(self) -> list[BasketLine]:
        stored = await self._stored_lines()
        items = await self._item_map(stored)
        return [_line_from_document(line, items.get(line.get("itemId"))) for line in stored]

    async def add(self, item: dict[str, Any], quantity: int, variant_index: int | None = None) -> BasketLine:
        """Add a line, merging with an identical one rather than duplicating it."""
        quantity = max(1, min(int(quantity or 1), MAX_LINE_QUANTITY))
        stored = await self._stored_lines()
        new_line = build_cart_line(item, _AddRequest(quantity, variant_index))

        existing = next((line for line in stored if cart_line_key(line) == cart_line_key(new_line)), None)
        if existing:
            existing["quantity"] = min(int(existing.get("quantity", 0)) + quantity, MAX_LINE_QUANTITY)
            existing.setdefault("lineId", new_line["lineId"])
            merged = existing
        else:
            if len(stored) >= MAX_BASKET_LINES:
                raise ValueError(f"A basket can hold at most {MAX_BASKET_LINES} different lines.")
            stored.append(new_line)
            merged = new_line

        await self._write_lines(stored)
        return _line_from_document(merged, item)

    async def set_quantity(self, line_ref: str, quantity: int) -> BasketLine | None:
        stored = await self._stored_lines()
        target = find_cart_line({"items": stored}, line_ref)
        if not target:
            return None
        target["quantity"] = max(1, min(int(quantity or 1), MAX_LINE_QUANTITY))
        await self._write_lines(stored)
        items = await self._item_map([target])
        return _line_from_document(target, items.get(target.get("itemId")))

    async def remove(self, line_ref: str) -> BasketLine | None:
        stored = await self._stored_lines()
        target = find_cart_line({"items": stored}, line_ref)
        if not target:
            return None
        items = await self._item_map([target])
        removed = _line_from_document(target, items.get(target.get("itemId")))
        await self._write_lines([line for line in stored if line is not target])
        return removed

    async def clear(self) -> int:
        stored = await self._stored_lines()
        await self._write_lines([])
        return len(stored)

    async def get_checkout_draft(self) -> dict[str, Any]:
        raise NotImplementedError

    async def set_checkout_draft(self, values: dict[str, Any]) -> dict[str, Any]:
        """Merge new values over the stored ones, ignoring blanks.

        Merging rather than replacing means the agent can fill in one field at a time
        across several turns without wiping what the customer already gave it.
        """
        current = await self.get_checkout_draft()
        incoming = normalize_checkout_draft(values)
        merged = dict(current)
        for field, value in incoming.items():
            if value:
                merged[field] = value
        await self._write_checkout_draft(merged)
        return merged

    async def _write_checkout_draft(self, draft: dict[str, Any]) -> None:
        raise NotImplementedError

    async def summary(self) -> dict[str, Any]:
        lines = await self.lines()
        subtotal = round(sum(line.subtotal for line in lines), 2)
        currency = lines[0].currency if lines else ((self.tenant.get("settings") or {}).get("currency") or "PKR")
        return {
            "kind": self.kind,
            "identity": self.identity.public_dict(),
            "lines": [line.public_dict() for line in lines],
            "lineCount": len(lines),
            "itemCount": sum(line.quantity for line in lines),
            "subtotal": subtotal,
            "currency": currency,
            "isEmpty": not lines,
        }


class CartBasket(_BaseBasket):
    """The customer's real cart. What the chat changes, the cart page shows."""

    kind = "cart"

    def __init__(self, tenant: dict[str, Any], identity: BasketIdentity, customer_user_id: ObjectId) -> None:
        super().__init__(tenant, identity)
        self.customerUserId = customer_user_id

    async def _cart_document(self) -> dict[str, Any] | None:
        db = get_database()
        return await db.carts.find_one(
            {"customerUserId": self.customerUserId, "tenantId": self.tenantId, "status": "active"}
        )

    async def _stored_lines(self) -> list[dict[str, Any]]:
        cart = await self._cart_document()
        return list(cart.get("items", [])) if cart else []

    async def _write_lines(self, lines: list[dict[str, Any]]) -> None:
        db = get_database()
        now = datetime.now(timezone.utc)
        cart = await self._cart_document()
        if cart:
            await db.carts.update_one({"_id": cart["_id"]}, {"$set": {"items": lines, "updatedAt": now}})
            return
        await db.carts.insert_one(
            {
                "customerUserId": self.customerUserId,
                "tenantId": self.tenantId,
                "items": lines,
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        )


    async def get_checkout_draft(self) -> dict[str, Any]:
        cart = await self._cart_document()
        return normalize_checkout_draft((cart or {}).get("checkoutDraft"))

    async def _write_checkout_draft(self, draft: dict[str, Any]) -> None:
        db = get_database()
        now = datetime.now(timezone.utc)
        cart = await self._cart_document()
        if cart:
            await db.carts.update_one({"_id": cart["_id"]}, {"$set": {"checkoutDraft": draft, "updatedAt": now}})
            return
        await db.carts.insert_one(
            {
                "customerUserId": self.customerUserId,
                "tenantId": self.tenantId,
                "items": [],
                "checkoutDraft": draft,
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        )


class DraftBasket(_BaseBasket):
    """A basket for someone with no account, held on the conversation.

    Deliberately stored under ``basketDraft`` rather than in ``pendingOrderDraft``: that
    field is the one-shot suggestion the existing chat UI renders, and overwriting it
    with accumulated lines would change what every current channel displays.
    """

    kind = "draft"

    def __init__(self, tenant: dict[str, Any], identity: BasketIdentity, conversation_id: ObjectId) -> None:
        super().__init__(tenant, identity)
        self.conversationId = conversation_id

    async def _stored_lines(self) -> list[dict[str, Any]]:
        db = get_database()
        conversation = await db.conversations.find_one({"_id": self.conversationId}, {"basketDraft": 1})
        return list(((conversation or {}).get("basketDraft") or {}).get("items", []))

    async def _write_lines(self, lines: list[dict[str, Any]]) -> None:
        db = get_database()
        now = datetime.now(timezone.utc)
        await db.conversations.update_one(
            {"_id": self.conversationId},
            {"$set": {"basketDraft": {"items": lines, "updatedAt": now}, "updatedAt": now}},
        )


    async def get_checkout_draft(self) -> dict[str, Any]:
        db = get_database()
        conversation = await db.conversations.find_one({"_id": self.conversationId}, {"checkoutDraft": 1})
        return normalize_checkout_draft((conversation or {}).get("checkoutDraft"))

    async def _write_checkout_draft(self, draft: dict[str, Any]) -> None:
        db = get_database()
        now = datetime.now(timezone.utc)
        await db.conversations.update_one(
            {"_id": self.conversationId},
            {"$set": {"checkoutDraft": draft, "updatedAt": now}},
        )


# ----------------------------------------------------------------- identity resolution --

# Each resolver answers "whose basket is this?" or defers. They are tried in order, so a
# stronger proof of identity wins over a weaker one. A magic-link resolver would slot in
# here between the session and the phone without touching anything else.
IdentityResolver = Callable[[dict[str, Any], dict[str, Any]], Awaitable[BasketIdentity | None]]


async def _resolve_from_session(tenant: dict[str, Any], context: dict[str, Any]) -> BasketIdentity | None:
    """A signed-in customer proved who they are with a token. Strongest signal."""
    customer_user = context.get("customer_user")
    if not customer_user or not customer_user.get("_id"):
        return None
    return BasketIdentity(
        channel=context.get("channel", "customer_portal"),
        tenantId=str(tenant["_id"]),
        kind="cart",
        customerUserId=str(customer_user["_id"]),
        conversationId=str(context.get("conversation_id") or ""),
        phone=str(customer_user.get("phone") or ""),
        linkedBy=LINKED_BY_SESSION,
    )


async def _resolve_from_phone(tenant: dict[str, Any], context: dict[str, Any]) -> BasketIdentity | None:
    """Link a WhatsApp number to the account that owns it.

    The sender's number is asserted by the WhatsApp provider, which makes it good
    evidence of *who is typing* - but the number stored on an account is whatever that
    account typed in. If an account claimed a number it does not own, the real owner
    messaging on WhatsApp would land in the impostor's cart.

    So the link requires the account to have verified the number, unless an operator
    deliberately relaxes that for a local demo. A basket holds no payment details, but a
    wrong link is still a wrong link.
    """
    phone = normalize_optional_pk_phone_or_blank(context.get("phone") or "")
    if not phone:
        return None

    db = get_database()
    query: dict[str, Any] = {"phone": phone, "accountType": "customer", "status": "active"}
    if settings.whatsapp_cart_link_requires_verified_phone:
        query["isPhoneVerified"] = True
    customer_user = await db.users.find_one(query)
    if not customer_user:
        return None

    logger.info(
        "Linked %s basket to customer account by phone (verified=%s).",
        context.get("channel", "whatsapp"),
        customer_user.get("isPhoneVerified", False),
    )
    return BasketIdentity(
        channel=context.get("channel", "whatsapp"),
        tenantId=str(tenant["_id"]),
        kind="cart",
        customerUserId=str(customer_user["_id"]),
        conversationId=str(context.get("conversation_id") or ""),
        phone=phone,
        linkedBy=LINKED_BY_PHONE,
    )


async def _resolve_anonymous(tenant: dict[str, Any], context: dict[str, Any]) -> BasketIdentity | None:
    """No account, and that is allowed. The conversation holds the basket.

    This is what lets a WhatsApp-only customer order without ever signing up.
    """
    conversation_id = context.get("conversation_id")
    if not conversation_id:
        return None
    return BasketIdentity(
        channel=context.get("channel", "website"),
        tenantId=str(tenant["_id"]),
        kind="draft",
        conversationId=str(conversation_id),
        phone=normalize_optional_pk_phone_or_blank(context.get("phone") or ""),
        linkedBy=LINKED_BY_NONE,
    )


IDENTITY_RESOLVERS: list[IdentityResolver] = [
    _resolve_from_session,
    _resolve_from_phone,
    _resolve_anonymous,
]


def register_identity_resolver(resolver: IdentityResolver, *, before: IdentityResolver | None = None) -> None:
    """Add a way of identifying a basket owner.

    The seam for a magic-link flow: resolve the token to a customer, return a
    ``BasketIdentity`` with ``linkedBy="magic_link"``, and register it ahead of the
    phone resolver.
    """
    if before is not None and before in IDENTITY_RESOLVERS:
        IDENTITY_RESOLVERS.insert(IDENTITY_RESOLVERS.index(before), resolver)
        return
    IDENTITY_RESOLVERS.insert(max(len(IDENTITY_RESOLVERS) - 1, 0), resolver)


async def resolve_basket_identity(
    tenant: dict[str, Any],
    *,
    channel: str,
    customer_user: dict[str, Any] | None = None,
    conversation_id: ObjectId | str | None = None,
    phone: str = "",
) -> BasketIdentity | None:
    context = {
        "channel": channel,
        "customer_user": customer_user,
        "conversation_id": conversation_id,
        "phone": phone,
    }
    for resolver in IDENTITY_RESOLVERS:
        identity = await resolver(tenant, context)
        if identity is not None:
            return identity
    return None


async def resolve_basket(
    tenant: dict[str, Any],
    *,
    channel: str,
    customer_user: dict[str, Any] | None = None,
    conversation_id: ObjectId | str | None = None,
    phone: str = "",
) -> ConversationBasket | None:
    """The basket this conversation may act on, or None when there is nowhere to put one.

    Returning None rather than raising lets a read-only channel such as the owner
    preview run the agent without a basket at all.
    """
    identity = await resolve_basket_identity(
        tenant, channel=channel, customer_user=customer_user, conversation_id=conversation_id, phone=phone
    )
    if identity is None:
        return None

    if identity.kind == "cart":
        return CartBasket(tenant, identity, ObjectId(identity.customerUserId))
    return DraftBasket(tenant, identity, ObjectId(identity.conversationId))
