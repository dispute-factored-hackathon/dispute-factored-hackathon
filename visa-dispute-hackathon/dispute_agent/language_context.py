"""Trusted language and locale context shared by GUI and voice channels."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .openai_interpreter import CallOpening

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
    "united states of america": ("en", "en-US"),
}


def _normalize_country(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(normalized.casefold().split())


@dataclass(frozen=True)
class ConversationLocaleContext:
    """Normalized channel-independent language context."""

    country: str | None
    language: str
    locale: str
    accent: str
    source: str
    fallback_reason: str | None = None
    country_is_ambiguous: bool = False

    @classmethod
    def from_gui_record(
        cls,
        *,
        country: str | None,
        preferred_language: str | None,
        locale: str | None,
    ) -> ConversationLocaleContext:
        """Resolve trusted database fields without an inference-model call."""

        language = (preferred_language or "").strip().casefold()
        stored_locale = (locale or "").strip()
        if language in SUPPORTED_LOCALES and stored_locale in SUPPORTED_LOCALES[language]:
            return cls(country, language, stored_locale, LOCALE_ACCENTS[stored_locale], "database")
        if language in DEFAULT_LOCALES and not stored_locale:
            return cls(
                country,
                language,
                DEFAULT_LOCALES[language],
                LOCALE_ACCENTS[DEFAULT_LOCALES[language]],
                "database_language_default_locale",
                "missing_locale",
            )

        country_default = COUNTRY_DEFAULTS.get(_normalize_country(country))
        if country_default:
            fallback_reason = (
                "invalid_or_inconsistent_stored_preferences"
                if language or stored_locale
                else "missing_stored_preferences"
            )
            default_language, default_locale = country_default
            return cls(
                country,
                default_language,
                default_locale,
                LOCALE_ACCENTS[default_locale],
                "country_default",
                fallback_reason,
            )
        return cls(
            country,
            "en",
            "en-US",
            "american",
            "product_default",
            "unsupported_country_or_preferences",
        )

    @classmethod
    def from_voice_opening(cls, opening: CallOpening) -> ConversationLocaleContext:
        """Normalize the schema-validated output of the voice opening model."""

        return cls(
            country=opening.country_name,
            language=opening.primary_language,
            locale=opening.locale,
            accent=LOCALE_ACCENTS[opening.locale],
            source="voice_country_code_inference",
            country_is_ambiguous=opening.country_is_ambiguous,
        )

    @classmethod
    def from_customer_record(
        cls, *, country: str | None, detected_accent: str | None
    ) -> ConversationLocaleContext:
        """Use the authenticated customer's country and compatible accent."""

        base = cls.from_gui_record(country=country, preferred_language=None, locale=None)
        normalized_accent = (detected_accent or "").strip().casefold().replace("-", "_")
        accent_locale = ACCENT_LOCALES.get(normalized_accent)
        if accent_locale in SUPPORTED_LOCALES[base.language]:
            return cls(
                country=country,
                language=base.language,
                locale=accent_locale,
                accent=LOCALE_ACCENTS[accent_locale],
                source="customer_record",
            )
        return cls(
            country=country,
            language=base.language,
            locale=base.locale,
            accent=base.accent,
            source="customer_country_default",
            fallback_reason=("missing_or_incompatible_customer_accent"),
        )

    @classmethod
    def explicit_choice(cls, language: str, accent: str | None = None) -> ConversationLocaleContext:
        """Validate an explicit customer language/accent change."""

        normalized_language = language.strip().casefold()
        if normalized_language not in DEFAULT_LOCALES:
            raise ValueError("language must be en, pt, or es")
        normalized_accent = (accent or "").strip().casefold().replace("-", "_")
        locale = ACCENT_LOCALES.get(normalized_accent, DEFAULT_LOCALES[normalized_language])
        if locale not in SUPPORTED_LOCALES[normalized_language]:
            raise ValueError("accent is not compatible with the selected language")
        return cls(
            country=None,
            language=normalized_language,
            locale=locale,
            accent=LOCALE_ACCENTS[locale],
            source="explicit_customer_choice",
        )
