"""Password strength rules shared by every path that accepts a password.

Enforced server-side. Client-side checks exist only to give faster feedback and
are never the control: registration, OTP-backed reset, and password change all
route through :func:`validate_password_strength` before hashing.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
REQUIRED_CHARACTER_CLASSES = 3

# Passwords seen constantly in credential-stuffing lists, plus the ones this project
# has shipped in demos and docs. Compared case-insensitively.
COMMON_PASSWORDS = frozenset(
    {
        "123456", "1234567", "12345678", "123456789", "1234567890", "12345",
        "password", "password1", "password123", "passw0rd", "p@ssw0rd", "p@ssword",
        "qwerty", "qwerty123", "qwertyuiop", "abc123", "abcd1234", "a1b2c3d4",
        "111111", "000000", "1111111111", "123123", "654321", "121212",
        "iloveyou", "admin", "admin123", "administrator", "root", "toor",
        "letmein", "welcome", "welcome1", "monkey", "dragon", "sunshine",
        "football", "baseball", "master", "shadow", "superman", "trustno1",
        "whatever", "zaq12wsx", "asdfghjkl", "1q2w3e4r", "1qaz2wsx",
        "pakistan", "pakistan123", "karachi", "lahore", "islamabad",
        "demo@12345", "admin@12345", "test1234", "changeme", "secret",
        "bizxus", "bizxusai", "bizxus123", "bizxusai123",
    }
)

_SYMBOL_PATTERN = re.compile(r"[^A-Za-z0-9]")


def _character_classes(password: str) -> int:
    return sum(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            bool(_SYMBOL_PATTERN.search(password)),
        )
    )


def _is_single_repeated_character(password: str) -> bool:
    return len(set(password)) == 1


def _is_simple_sequence(password: str) -> bool:
    """Catch runs like 12345678 or abcdefgh that pass a naive class count."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return False
    deltas = {ord(b) - ord(a) for a, b in zip(password, password[1:])}
    return deltas in ({1}, {-1})


def _contains_identity(password: str, *identity_parts: str | None) -> bool:
    lowered = password.lower()
    for part in identity_parts:
        candidate = str(part or "").strip().lower()
        if "@" in candidate:
            candidate = candidate.split("@", 1)[0]
        for token in re.split(r"[^a-z0-9]+", candidate):
            if len(token) >= 4 and token in lowered:
                return True
    return False


def describe_password_problem(password: str, *identity_parts: str | None) -> str | None:
    """Return a human-readable reason the password is unacceptable, or None if it passes."""
    value = str(password or "")

    if len(value) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(value) > MAX_PASSWORD_LENGTH:
        return f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer."
    if len(value.encode("utf-8")) > 72:
        return "Password must be 72 UTF-8 bytes or fewer. Use a shorter password."
    if value.strip() != value:
        return "Password cannot start or end with a space."
    if value.lower() in COMMON_PASSWORDS:
        return "This password is too common and appears in known breach lists. Choose something unique."
    if _is_single_repeated_character(value):
        return "Password cannot be the same character repeated."
    if _is_simple_sequence(value):
        return "Password cannot be a simple sequence such as 12345678."
    if _character_classes(value) < REQUIRED_CHARACTER_CLASSES:
        return (
            "Password must include at least three of: lowercase letter, uppercase letter, "
            "number, and symbol."
        )
    if _contains_identity(value, *identity_parts):
        return "Password cannot contain your name, email, or phone number."
    return None


def is_password_acceptable(password: str, *identity_parts: str | None) -> bool:
    return describe_password_problem(password, *identity_parts) is None


def validate_password_strength(password: str, *identity_parts: str | None) -> None:
    """Raise 422 when the password fails policy. Call before hashing, always."""
    problem = describe_password_problem(password, *identity_parts)
    if problem:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=problem)
