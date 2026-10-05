import ipaddress
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

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
COUNTRY_IS_BASE_URL = "https://api.country.is"


@dataclass(frozen=True)
class _CountryCacheEntry:
    country_code: str | None
    expires_at: float


class CountryIsLookup:
    """Resolve public IPs without making localization a page-load dependency."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: float | None = None,
        failure_ttl_seconds: float | None = None,
        max_cache_entries: int | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("COUNTRY_IS_TIMEOUT_SECONDS", "0.6")
        )
        self.cache_ttl_seconds = cache_ttl_seconds or float(
            os.getenv("COUNTRY_IS_CACHE_TTL_SECONDS", "86400")
        )
        self.failure_ttl_seconds = failure_ttl_seconds or float(
            os.getenv("COUNTRY_IS_FAILURE_TTL_SECONDS", "300")
        )
        self.max_cache_entries = max_cache_entries or int(
            os.getenv("COUNTRY_IS_CACHE_MAX_ENTRIES", "1024")
        )
        self.client = client or httpx.Client(
            base_url=COUNTRY_IS_BASE_URL,
            headers={"User-Agent": "factored-bank-demo/1.0"},
        )
        self._cache: OrderedDict[str, _CountryCacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def lookup(self, raw_ip: str | None) -> str | None:
        public_ip = self._public_ip(raw_ip)
        if public_ip is None:
            return None

        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(public_ip)
            if cached is not None and cached.expires_at > now:
                self._cache.move_to_end(public_ip)
                return cached.country_code
            self._cache.pop(public_ip, None)

        country_code: str | None = None
        try:
            response = self.client.get(
                f"/{public_ip}",
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            candidate = str(response.json().get("country", "")).strip().upper()
            if len(candidate) == 2 and candidate.isalpha():
                country_code = candidate
        except (httpx.HTTPError, TypeError, ValueError):
            country_code = None

        ttl = self.cache_ttl_seconds if country_code is not None else self.failure_ttl_seconds
        with self._lock:
            self._cache[public_ip] = _CountryCacheEntry(
                country_code=country_code,
                expires_at=now + ttl,
            )
            self._cache.move_to_end(public_ip)
            while len(self._cache) > self.max_cache_entries:
                self._cache.popitem(last=False)
        return country_code

    @staticmethod
    def _public_ip(raw_ip: str | None) -> str | None:
        if not raw_ip:
            return None
        try:
            address = ipaddress.ip_address(raw_ip.split("%", maxsplit=1)[0].strip())
        except ValueError:
            return None
        return address.compressed if address.is_global else None


country_lookup = CountryIsLookup()


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


def country_for_request(
    headers: Mapping[str, str],
    client_ip: str | None,
    *,
    lookup: CountryIsLookup = country_lookup,
) -> tuple[str | None, str]:
    country_code, source = country_from_headers(headers)
    if country_code is not None:
        return country_code, source
    country_code = lookup.lookup(client_ip)
    if country_code is not None:
        return country_code, "country.is"
    return None, "default"


def language_for_locale(locale: InterfaceLocale) -> str:
    return locale.value.split("-", maxsplit=1)[0]
