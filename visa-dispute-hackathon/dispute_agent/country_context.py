"""Validation for the only caller-context input: a telephone country code."""

from __future__ import annotations


def normalize_country_code(value: str) -> str:
    """Return an E.164-style calling code without inferring a country locally."""

    digits = "".join(character for character in value if character.isdigit())
    if not digits or len(digits) > 3:
        raise ValueError("country code must contain one to three digits, for example +55")
    return f"+{digits}"
