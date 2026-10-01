from collections.abc import Mapping

from webapp.backend.models.customer import InterfaceLocale

PORTUGUESE_COUNTRIES = frozenset({"AO", "BR", "CV", "GW", "MZ", "PT", "ST", "TL"})
SPANISH_COUNTRIES = frozenset(
    {
        "AR",
        "BO",
        "CL",
        "CO",
        "CR",
        "CU",
        "DO",
        "EC",
        "ES",
        "GT",
        "HN",
        "MX",
        "NI",
        "PA",
        "PE",
        "PR",
        "PY",
        "SV",
        "UY",
        "VE",
    }
)
REGIONAL_SPANISH_LOCALES = {
    "AR": InterfaceLocale.ARGENTINE_SPANISH,
    "CO": InterfaceLocale.COLOMBIAN_SPANISH,
    "MX": InterfaceLocale.MEXICAN_SPANISH,
}
COUNTRY_HEADER_NAMES = (
    "cf-ipcountry",
    "cloudfront-viewer-country",
    "x-vercel-ip-country",
    "x-factored-country",
)


def locale_for_country(country_code: str | None) -> InterfaceLocale:
    normalized = (country_code or "").strip().upper()
    if normalized in PORTUGUESE_COUNTRIES:
        return InterfaceLocale.PORTUGUESE
    if normalized in SPANISH_COUNTRIES:
        return REGIONAL_SPANISH_LOCALES.get(normalized, InterfaceLocale.SPANISH)
    return InterfaceLocale.ENGLISH


def country_from_headers(headers: Mapping[str, str]) -> tuple[str | None, str]:
    for header_name in COUNTRY_HEADER_NAMES:
        value = headers.get(header_name)
        if value and value.upper() not in {"XX", "T1"}:
            return value.upper(), header_name
    return None, "default"


def language_for_locale(locale: InterfaceLocale) -> str:
    return locale.value.split("-", maxsplit=1)[0]
