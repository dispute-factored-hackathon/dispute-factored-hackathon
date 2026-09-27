"""Country-code context used only to localize the opening language prompt."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryContext:
    calling_code: str
    country_en: str
    country_es: str
    country_pt: str
    opening_language: str


COUNTRIES = {
    "+1": CountryContext("+1", "the United States", "Estados Unidos", "os Estados Unidos", "en"),
    "+34": CountryContext("+34", "Spain", "España", "a Espanha", "es"),
    "+44": CountryContext("+44", "the United Kingdom", "Reino Unido", "o Reino Unido", "en"),
    "+51": CountryContext("+51", "Peru", "Perú", "o Peru", "es"),
    "+52": CountryContext("+52", "Mexico", "México", "o México", "es"),
    "+53": CountryContext("+53", "Cuba", "Cuba", "Cuba", "es"),
    "+54": CountryContext("+54", "Argentina", "Argentina", "a Argentina", "es"),
    "+55": CountryContext("+55", "Brazil", "Brasil", "o Brasil", "pt"),
    "+56": CountryContext("+56", "Chile", "Chile", "o Chile", "es"),
    "+57": CountryContext("+57", "Colombia", "Colombia", "a Colômbia", "es"),
    "+58": CountryContext("+58", "Venezuela", "Venezuela", "a Venezuela", "es"),
    "+81": CountryContext("+81", "Japan", "Japón", "o Japão", "en"),
    "+351": CountryContext("+351", "Portugal", "Portugal", "Portugal", "pt"),
    "+502": CountryContext("+502", "Guatemala", "Guatemala", "a Guatemala", "es"),
    "+503": CountryContext("+503", "El Salvador", "El Salvador", "El Salvador", "es"),
    "+504": CountryContext("+504", "Honduras", "Honduras", "Honduras", "es"),
    "+505": CountryContext("+505", "Nicaragua", "Nicaragua", "a Nicarágua", "es"),
    "+506": CountryContext("+506", "Costa Rica", "Costa Rica", "a Costa Rica", "es"),
    "+507": CountryContext("+507", "Panama", "Panamá", "o Panamá", "es"),
    "+593": CountryContext("+593", "Ecuador", "Ecuador", "o Equador", "es"),
    "+595": CountryContext("+595", "Paraguay", "Paraguay", "o Paraguai", "es"),
    "+598": CountryContext("+598", "Uruguay", "Uruguay", "o Uruguai", "es"),
}


def normalize_country_code(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if not digits or len(digits) > 3:
        raise ValueError("country code must contain one to three digits, for example +55")
    return f"+{digits}"


def country_context(value: str) -> CountryContext | None:
    return COUNTRIES.get(normalize_country_code(value))


def opening_prompt(value: str) -> str:
    code = normalize_country_code(value)
    context = COUNTRIES.get(code)
    if context is None:
        return (
            f"Hi! You've reached Bank Factored. We see you're calling from country code {code}. "
            "Would you like to continue in English, Spanish, or Portuguese?"
        )
    if context.opening_language == "es":
        if code == "+57":
            return (
                "¡Hola! Se ha comunicado con Bank Factored. Vemos que llama desde Colombia. "
                "¿Desea continuar esta llamada en español, inglés o portugués?"
            )
        if code == "+52":
            return (
                "¡Hola! Gracias por llamar a Bank Factored. Vemos que llama desde México. "
                "¿Desea continuar esta llamada en español, inglés o portugués?"
            )
        if code == "+54":
            return (
                "¡Hola! Te comunicaste con Bank Factored. Vemos que llamás desde Argentina. "
                "¿Querés continuar esta llamada en español, inglés o portugués?"
            )
        return (
            f"¡Hola! Se ha comunicado con Bank Factored. Vemos que llama desde {context.country_es}. "
            "¿Desea continuar esta llamada en español, inglés o portugués?"
        )
    if context.opening_language == "pt":
        country_origin = context.country_pt
        if country_origin.startswith("o "):
            country_origin = f"do {country_origin[2:]}"
        elif country_origin.startswith("a "):
            country_origin = f"da {country_origin[2:]}"
        elif country_origin.startswith("os "):
            country_origin = f"dos {country_origin[3:]}"
        elif country_origin.startswith("as "):
            country_origin = f"das {country_origin[3:]}"
        else:
            country_origin = f"de {country_origin}"
        return (
            f"Olá! Você ligou para o Bank Factored. Identificamos que você está ligando {country_origin}. "
            "Gostaria de continuar esta ligação em português, inglês ou espanhol?"
        )
    return (
        f"Hi! You've reached Bank Factored. We see you're calling from {context.country_en}. "
        "Would you like to continue in English, Spanish, or Portuguese?"
    )


def locale_for(language: str, country_code: str | None) -> str:
    """Choose a supported regional locale without overriding the chosen language."""

    if language == "en":
        return "en-US"
    if language == "pt":
        return "pt-BR"
    if language == "es":
        regional_spanish = {
            "+54": "es-AR",
            "+52": "es-MX",
            "+57": "es-CO",
        }
        if country_code:
            try:
                return regional_spanish.get(normalize_country_code(country_code), "es-419")
            except ValueError:
                pass
        return "es-419"
    return "en-US"
