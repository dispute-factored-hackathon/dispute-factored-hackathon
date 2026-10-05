import json
from pathlib import Path

import httpx
import pytest
from fakes import (
    complaint_repository,
    customer_repository,
    product_repository,
    session_repository,
    transaction_repository,
)
from fastapi.testclient import TestClient

from webapp.backend.main import app
from webapp.backend.services.localization import (
    CountryIsLookup,
    country_for_request,
    country_lookup,
    locale_for_country,
)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "webapp" / "frontend"
LOCALES_DIR = FRONTEND_DIR / "locales" / "v1"


def clear_repositories() -> None:
    customer_repository._customers.clear()
    product_repository._products.clear()
    transaction_repository._transactions.clear()
    complaint_repository._complaints.clear()
    session_repository._sessions.clear()


def setup_function() -> None:
    clear_repositories()


def teardown_function() -> None:
    clear_repositories()


@pytest.mark.parametrize(
    ("country_code", "expected_locale"),
    [
        ("BR", "pt-BR"),
        ("PT", "pt-BR"),
        ("MX", "es-MX"),
        ("CO", "es-CO"),
        ("AR", "es-AR"),
        ("PE", "es-419"),
        ("US", "en-US"),
        (None, "en-US"),
    ],
)
def test_country_defaults_to_supported_locale(
    country_code: str | None,
    expected_locale: str,
) -> None:
    assert locale_for_country(country_code).value == expected_locale


def test_locale_context_uses_edge_country_header() -> None:
    response = TestClient(app).get(
        "/api/localization/context",
        headers={"CF-IPCountry": "BR"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "locale": "pt-BR",
        "language": "pt",
        "country_code": "BR",
        "source": "cf-ipcountry",
    }


def test_locale_context_falls_back_to_english_without_country() -> None:
    response = TestClient(app).get("/api/localization/context")

    assert response.status_code == 200
    assert response.json()["locale"] == "en-US"
    assert response.json()["source"] == "default"


def test_locale_context_uses_country_is_for_a_public_client_ip(monkeypatch) -> None:
    seen_ips: list[str | None] = []

    def lookup(client_ip: str | None) -> str | None:
        seen_ips.append(client_ip)
        return "MX"

    monkeypatch.setattr(country_lookup, "lookup", lookup)
    response = TestClient(app, client=("8.8.8.8", 50000)).get(
        "/api/localization/context"
    )

    assert response.status_code == 200
    assert response.json() == {
        "locale": "es-MX",
        "language": "es",
        "country_code": "MX",
        "source": "country.is",
    }
    assert seen_ips == ["8.8.8.8"]


def test_country_is_lookup_is_cached_and_uses_a_short_timeout() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ip": "8.8.8.8", "country": "BR"})

    lookup = CountryIsLookup(
        client=httpx.Client(
            base_url="https://api.country.is",
            transport=httpx.MockTransport(handler),
        ),
        timeout_seconds=0.2,
        cache_ttl_seconds=3600,
    )

    assert lookup.lookup("8.8.8.8") == "BR"
    assert lookup.lookup("8.8.8.8") == "BR"
    assert len(requests) == 1
    assert requests[0].url == httpx.URL("https://api.country.is/8.8.8.8")
    assert requests[0].extensions["timeout"]["read"] == 0.2


def test_country_headers_take_priority_over_external_lookup() -> None:
    class FailingLookup:
        @staticmethod
        def lookup(_client_ip: str | None) -> str | None:
            raise AssertionError("country.is must not be called when an edge header exists")

    country_code, source = country_for_request(
        {"cf-ipcountry": "CO"},
        "8.8.8.8",
        lookup=FailingLookup(),  # type: ignore[arg-type]
    )

    assert country_code == "CO"
    assert source == "cf-ipcountry"


def test_country_is_failure_and_non_public_ip_fall_back_to_english() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    lookup = CountryIsLookup(
        client=httpx.Client(
            base_url="https://api.country.is",
            transport=httpx.MockTransport(handler),
        ),
        timeout_seconds=0.2,
        failure_ttl_seconds=60,
    )

    private_result = country_for_request({}, "127.0.0.1", lookup=lookup)
    failed_result = country_for_request({}, "8.8.4.4", lookup=lookup)
    cached_failure = country_for_request({}, "8.8.4.4", lookup=lookup)

    assert private_result == (None, "default")
    assert failed_result == (None, "default")
    assert cached_failure == (None, "default")
    assert calls == 1


def test_all_locale_resources_have_the_same_message_keys() -> None:
    resources = {
        language: json.loads((LOCALES_DIR / f"{language}.json").read_text())
        for language in ("en", "pt", "es")
    }

    assert set(resources["pt"]) == set(resources["en"])
    assert set(resources["es"]) == set(resources["en"])
    assert len(resources["en"]) >= 250


def test_customer_pages_load_shared_localization_layer() -> None:
    scripts = list((FRONTEND_DIR / "js" / "pages").glob("*.js"))

    assert scripts
    for script in scripts:
        assert "i18n.js?v=1" in script.read_text(), script.name


def test_profile_creation_offers_five_language_and_accent_options() -> None:
    signup = (FRONTEND_DIR / "pages" / "signup.html").read_text()
    profile = (FRONTEND_DIR / "pages" / "profile.html").read_text()

    for page in (signup, profile):
        assert page.count('<option value="en-US">') == 1
        assert page.count('<option value="pt-BR">') == 1
        assert page.count('<option value="es-AR">') == 1
        assert page.count('<option value="es-CO">') == 1
        assert page.count('<option value="es-MX">') == 1
        assert '<option value="es-419">' not in page


def test_factored_login_uses_locale_selected_during_signup() -> None:
    client = TestClient(app)
    factored_id = "918273"
    create_response = client.post(
        "/api/customers",
        json={
            "first_name": "Cliente",
            "last_name": "Sintético",
            "date_of_birth": "1990-05-20",
            "gender": "prefer_not_to_say",
            "mobile_phone": "+573009182733",
            "preferred_accent": "colombian_spanish",
            "preferred_locale": "es-419",
            "factored_id": factored_id,
        },
    )
    assert create_response.status_code == 201

    response = client.post("/api/auth/login", json={"factored_id": factored_id})

    assert response.status_code == 200
    assert response.json()["customer"]["locale"] == "es-419"
    assert response.json()["customer"]["locale_source"] == "customer"
