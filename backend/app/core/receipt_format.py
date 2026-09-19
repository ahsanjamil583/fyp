"""Formatting shared by every receipt the platform prints.

Payment receipts and order receipts are different documents for different purposes, but
an amount, a date and an escaped field must look the same on both. These live below the
service layer so neither receipt builder has to import the other's module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any


def format_receipt_money(value: Any, currency: str = "PKR") -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{escape(str(currency or 'PKR'))} {amount:,.2f}"


def format_receipt_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return escape(str(value or "-"))


def receipt_text(value: Any, default: str = "-") -> str:
    """Every value on a receipt goes through here.

    A receipt is rendered as HTML from data a customer supplied - their own name, their
    address, an order note - so escaping is not optional.
    """
    text = str(value if value not in [None, ""] else default)
    return escape(text)
