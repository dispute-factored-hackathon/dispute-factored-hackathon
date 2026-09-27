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
            return cls(country, language, stored_locale, "database")
        if language in DEFAULT_LOCALES and not stored_locale:
            return cls(
                country,
                language,
                DEFAULT_LOCALES[language],
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
            return cls(country, *country_default, "country_default", fallback_reason)
        return cls(
            country,
            "en",
            "en-US",
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
            source="voice_country_code_inference",
            country_is_ambiguous=opening.country_is_ambiguous,
        )
