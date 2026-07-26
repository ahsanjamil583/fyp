from __future__ import annotations

import re
from typing import Any


def normalize_excel_header(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    aliases = {
        "name": "name",
        "item name": "name",
        "product name": "name",
        "title": "name",
        "category": "category",
        "category name": "category",
        "description": "description",
        "desc": "description",
        "price": "price",
        "base price": "price",
        "sale price": "price",
        "cost price": "costPrice",
        "cost": "costPrice",
        "stock": "stockQuantity",
        "quantity": "stockQuantity",
        "qty": "stockQuantity",
        "stock quantity": "stockQuantity",
        "available stock": "stockQuantity",
        "inventory": "stockQuantity",
        "low stock threshold": "lowStockThreshold",
        "threshold": "lowStockThreshold",
        "tags": "tags",
        "tag": "tags",
        "color": "color",
        "colour": "color",
        "size": "size",
        "material": "material",
        "sku": "sku",
        "currency": "currency",
        "unit": "unit",
        "item type": "itemType",
        "type": "itemType",
        "status": "status",
        "image": "imageUrl",
        "image url": "imageUrl",
        "image link": "imageUrl",
        "photo": "imageUrl",
        "photo url": "imageUrl",
        "is sellable": "isSellable",
        "sellable": "isSellable",
        "is bookable": "isBookable",
        "bookable": "isBookable",
        "is stock tracked": "isStockTracked",
        "track stock": "isStockTracked",
        "service duration minutes": "serviceDurationMinutes",
        "duration": "serviceDurationMinutes",
        "service buffer minutes": "serviceBufferMinutes",
        "buffer": "serviceBufferMinutes",
        "service delivery mode": "serviceDeliveryMode",
        "delivery mode": "serviceDeliveryMode",
    }
    if text.startswith("custom "):
        return "custom." + text.replace("custom ", "", 1).replace(" ", "_")
    if text.startswith("custom."):
        return text
    return aliases.get(text, text.replace(" ", ""))


def is_short_confirmation(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    confirmations = {
        "g", "gee", "ji", "jee", "han", "haan", "yes", "ok", "okay", "theek", "done", "confirm",
        "g bana do", "ji bana do", "jee bana do", "haan bana do", "han bana do", "yes make it", "make draft", "draft bana do",
        "order bana do", "kar do", "kr do", "bana do", "banado", "yes order", "confirm order",
    }
    return normalized in confirmations or (len(normalized.split()) <= 3 and any(word in normalized.split() for word in ["bana", "confirm", "yes", "haan", "han", "ji", "g"]))


def likely_food_or_unavailable_keywords(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())
    tokens = set(normalized.split())
    return bool(tokens & {
        "burger", "burgers", "pizza", "biryani", "karhai", "pulao", "fries", "shawarma", "roll", "sandwich", "zinger",
        "medicine", "paracetamol", "phone", "iphone", "laptop",
    })
