import re

from fastapi import HTTPException, status

PAKISTAN_PROVINCES = [
    "Punjab",
    "Sindh",
    "Khyber Pakhtunkhwa",
    "Balochistan",
    "Islamabad Capital Territory",
    "Gilgit-Baltistan",
    "Azad Jammu and Kashmir",
]


def normalize_pk_phone(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""

    if digits.startswith("0092"):
        digits = digits[2:]
    if digits.startswith("92") and len(digits) >= 12:
        digits = f"0{digits[2:]}"
    if digits.startswith("3") and len(digits) == 10:
        digits = f"0{digits}"

    if not re.fullmatch(r"03\d{9}", digits):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use a valid Pakistan mobile number, for example 03001234567 or +923001234567.",
        )
    return digits


def normalize_optional_pk_phone(value: str) -> str:
    if not str(value or "").strip():
        return ""
    return normalize_pk_phone(value)


def normalize_optional_pk_phone_or_blank(value: str) -> str:
    if not str(value or "").strip():
        return ""
    try:
        return normalize_pk_phone(value)
    except HTTPException:
        return ""


def normalize_province(value: str) -> str:
    province = " ".join(str(value or "").strip().split())
    if not province:
        return ""

    for allowed in PAKISTAN_PROVINCES:
        if province.lower() == allowed.lower():
            return allowed

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Select a valid Pakistan province or territory.",
    )


def normalize_optional_email(value: str) -> str:
    return str(value or "").strip().lower()


def get_language_mode(settings: dict | None) -> str:
    configured = str((settings or {}).get("languageMode") or "mixed").strip().lower()
    return configured if configured in {"english", "mixed", "roman_urdu"} else "mixed"


def build_ai_localization_guidance(language_mode: str, tenant: dict) -> str:
    city = ((tenant.get("address") or {}).get("city") or "").strip()
    province = ((tenant.get("address") or {}).get("province") or "").strip()
    whatsapp = ((tenant.get("contact") or {}).get("whatsapp") or "").strip()
    phone = ((tenant.get("contact") or {}).get("phone") or "").strip()
    contact_hint = whatsapp or phone or "contact not shared yet"
    location_hint = ", ".join(part for part in [city, province, "Pakistan"] if part)

    if language_mode == "roman_urdu":
        return (
            "Reply in easy Roman Urdu. Keep sentences short and practical. "
            "Use PKR for prices, use local phrasing like WhatsApp, delivery, pickup, and location. "
            f"If contact is needed, prefer this business contact hint: {contact_hint}. "
            f"If location helps, use this business location hint: {location_hint or 'Pakistan'}."
        )
    if language_mode == "mixed":
        return (
            "Reply in mixed Roman Urdu plus simple English. Keep the answer easy for Pakistani customers to understand. "
            "Use PKR for prices and prefer local words like WhatsApp, pickup, delivery, and location."
        )
    return (
        "Reply in simple English that still fits Pakistani users. Use PKR for prices and prefer local business wording such as WhatsApp, pickup, delivery, and city."
    )


def evaluate_localized_reply(user_message: str, ai_text: str, language_mode: str, intent: str) -> dict:
    user_text = str(user_message or "").lower()
    reply_text = str(ai_text or "").lower()
    score = 0.0
    checks = {
        "matchesLanguageMode": False,
        "usesLocalBusinessTerms": False,
        "keepsActionClear": False,
        "mentionsCurrencyWhenNeeded": True,
    }

    roman_tokens = {"hai", "mujhe", "aap", "kar", "kya", "ji", "mil", "chahiye", "qeemat", "whatsapp"}
    local_terms = {"pkr", "whatsapp", "pickup", "delivery", "city", "location", "contact"}

    if language_mode == "english":
        checks["matchesLanguageMode"] = True
        score += 0.25
    else:
        if any(token in reply_text for token in roman_tokens):
            checks["matchesLanguageMode"] = True
            score += 0.25

    if any(token in reply_text for token in local_terms):
        checks["usesLocalBusinessTerms"] = True
        score += 0.25

    if any(token in reply_text for token in ["confirm", "batayein", "bata dein", "order", "draft", "contact", "pooch"]):
        checks["keepsActionClear"] = True
        score += 0.25

    if intent in {"ask_price", "place_order"} or "price" in user_text or "qeemat" in user_text:
        checks["mentionsCurrencyWhenNeeded"] = "pkr" in reply_text
        if checks["mentionsCurrencyWhenNeeded"]:
            score += 0.25
    else:
        score += 0.25

    return {
        "score": round(score, 2),
        "checks": checks,
        "passed": score >= 0.75,
    }


def localize_business_summary(
    *,
    tenant_name: str,
    language_mode: str,
    total_transactions: int,
    total_orders: int,
    gross_revenue: float,
    avg_order_value: float,
    top_item: str,
    marketplace_share: float,
    quote_approval_rate: float,
    momentum_note: str,
    low_stock_note: str,
) -> str:
    if language_mode == "roman_urdu":
        return (
            f"{tenant_name} ne ab tak {total_transactions} tracked transactions handle ki hain, jin mein {total_orders} orders shamil hain. "
            f"Gross revenue PKR {gross_revenue} hai aur average order value PKR {avg_order_value} hai. "
            f"Is waqt sab se strong item {top_item} hai. Marketplace share {marketplace_share}% hai aur quote approval {quote_approval_rate}% hai. "
            f"{momentum_note} {low_stock_note}"
        )
    if language_mode == "mixed":
        return (
            f"{tenant_name} ne {total_transactions} tracked transactions process kiye hain, including {total_orders} orders. "
            f"Gross revenue PKR {gross_revenue} hai aur average order value PKR {avg_order_value} hai. "
            f"Top performing item {top_item} hai. Marketplace share {marketplace_share}% aur quote approval {quote_approval_rate}% hai. "
            f"{momentum_note} {low_stock_note}"
        )
    return (
        f"{tenant_name} has processed {total_transactions} tracked transactions, including {total_orders} orders. "
        f"Gross revenue is PKR {gross_revenue} and average order value is PKR {avg_order_value}. "
        f"The strongest current item is {top_item}. Marketplace share is {marketplace_share}% and quote approval is {quote_approval_rate}%. "
        f"{momentum_note} {low_stock_note}"
    )
