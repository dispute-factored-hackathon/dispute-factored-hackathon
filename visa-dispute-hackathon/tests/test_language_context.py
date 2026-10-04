import pytest

from dispute_agent.language_context import ConversationLocaleContext


@pytest.mark.parametrize(
    ("accent", "locale", "language", "spoken_accent"),
    (
        ("english", "en-US", "en", "american"),
        ("portuguese", "pt-BR", "pt", "brazilian"),
        ("argentine_spanish", "es-AR", "es", "argentinian"),
        ("colombian_spanish", "es-CO", "es", "colombian"),
        ("mexican_spanish", "es-MX", "es", "mexican"),
    ),
)
def test_profile_accent_selects_registered_regional_voice(
    accent: str,
    locale: str,
    language: str,
    spoken_accent: str,
) -> None:
    context = ConversationLocaleContext.from_customer_record(
        country="Factoredland",
        detected_accent=accent,
    )

    assert (context.locale, context.language, context.accent) == (
        locale,
        language,
        spoken_accent,
    )


def test_explicit_profile_locale_takes_priority_over_country_code_region() -> None:
    context = ConversationLocaleContext.from_customer_record(
        country="Mexico",
        detected_accent="mexican_spanish",
        preferred_locale="es-AR",
    )

    assert (context.locale, context.accent, context.source) == (
        "es-AR",
        "argentinian",
        "customer_record",
    )


def test_legacy_neutral_spanish_prefers_the_profiles_regional_accent() -> None:
    context = ConversationLocaleContext.from_customer_record(
        country="Colombia",
        detected_accent="colombian_spanish",
        preferred_locale="es-419",
    )

    assert (context.locale, context.accent) == ("es-CO", "colombian")
