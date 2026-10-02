"""Trusted language and locale context shared by GUI and voice channels."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

SUPPORTED_LOCALES = {
    "en": {"en-US"},
    "pt": {"pt-BR", "pt-PT"},
    "es": {"es-419", "es-AR", "es-CO", "es-ES", "es-MX"},
}
DEFAULT_LOCALES = {"en": "en-US", "pt": "pt-BR", "es": "es-419"}
LOCALE_ACCENTS = {
    "en-US": "american",
    "pt-BR": "brazilian",
    "pt-PT": "portuguese",
    "es-419": "neutral_latin_american",
    "es-AR": "argentinian",
    "es-CO": "colombian",
    "es-ES": "spanish",
    "es-MX": "mexican",
}
ACCENT_LOCALES = {accent: locale for locale, accent in LOCALE_ACCENTS.items()}
COUNTRY_DEFAULTS = {
    "argentina": ("es", "es-AR"),
    "brasil": ("pt", "pt-BR"),
    "brazil": ("pt", "pt-BR"),
    "colombia": ("es", "es-CO"),
    "españa": ("es", "es-ES"),
    "espana": ("es", "es-ES"),
    "mexico": ("es", "es-MX"),
    "méxico": ("es", "es-MX"),
    "portugal": ("pt", "pt-PT"),
    "spain": ("es", "es-ES"),
    "united states": ("en", "en-US"),
}


def _normalize_country(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return " ".join(
        "".join(char for char in normalized if not unicodedata.combining(char)).casefold().split()
    )


@dataclass(frozen=True)
class ConversationLocaleContext:
    """Normalized channel-independent language context."""

    country: str | None
    language: str
    locale: str
    accent: str
    source: str
    fallback_reason: str | None = None

    @classmethod
    def from_customer_record(
        cls, *, country: str | None, detected_accent: str | None
    ) -> ConversationLocaleContext:
        language, locale = COUNTRY_DEFAULTS.get(_normalize_country(country), ("en", "en-US"))
        normalized_accent = (detected_accent or "").strip().casefold().replace("-", "_")
        accent_locale = ACCENT_LOCALES.get(normalized_accent)
        if accent_locale in SUPPORTED_LOCALES[language]:
            locale = accent_locale
        return cls(country, language, locale, LOCALE_ACCENTS[locale], "customer_record")

    @classmethod
    def from_calling_code(cls, calling_code: str | None) -> ConversationLocaleContext:
        country_by_code = {
            "+55": "Brazil",
            "+57": "Colombia",
            "+52": "Mexico",
            "+54": "Argentina",
            "+351": "Portugal",
            "+34": "Spain",
        }
        country = country_by_code.get(calling_code)
        language, locale = COUNTRY_DEFAULTS.get(_normalize_country(country), ("en", "en-US"))
        return cls(country, language, locale, LOCALE_ACCENTS[locale], "calling_code_hint")

    @classmethod
    def explicit_choice(cls, language: str, accent: str | None = None) -> ConversationLocaleContext:
        normalized_language = language.strip().casefold()
        if normalized_language not in DEFAULT_LOCALES:
            raise ValueError("language must be en, pt, or es")
        normalized_accent = (accent or "").strip().casefold().replace("-", "_")
        locale = ACCENT_LOCALES.get(normalized_accent, DEFAULT_LOCALES[normalized_language])
        if locale not in SUPPORTED_LOCALES[normalized_language]:
            raise ValueError("accent is not compatible with the selected language")
        return cls(None, normalized_language, locale, LOCALE_ACCENTS[locale], "customer_choice")
