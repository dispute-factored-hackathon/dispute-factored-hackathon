from fastapi.testclient import TestClient

from webapp.backend.main import app
from webapp.backend.repositories.mock import (
    complaint_repository,
    customer_repository,
    product_repository,
    session_repository,
    transaction_repository,
)


def clear_repositories() -> None:
    customer_repository._customers.clear()
    product_repository._products.clear()
    transaction_repository._transactions.clear()
    complaint_repository._complaints.clear()
    session_repository._sessions.clear()


def create_customer(
    client: TestClient,
    *,
    factored_id: str = "123456",
    first_name: str = "Gabriel",
    last_name: str = "Factored",
    phone: str = "+5511981020050",
    preferred_accent: str = "portuguese",
) -> dict:
    response = client.post(
        "/api/customers",
        json={
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": "2000-01-01",
            "gender": "male",
            "mobile_phone": phone,
            "preferred_accent": preferred_accent,
            "factored_id": factored_id,
        },
    )

    assert response.status_code == 201

    return response.json()


def login(
    client: TestClient,
    *,
    factored_id: str = "123456",
):
    return client.post(
        "/api/auth/login",
        json={
            "factored_id": factored_id,
        },
    )


def setup_function() -> None:
    clear_repositories()


def teardown_function() -> None:
    clear_repositories()


def test_login_with_valid_factored_id() -> None:
    client = TestClient(app)

    created = create_customer(
        client,
    )

    response = login(
        client,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["authenticated"] is True

    customer = body["customer"]

    assert customer["customer_id"] == created["customer_id"]

    assert customer["first_name"] == "Gabriel"
    assert customer["last_name"] == "Factored"

    assert customer["factored_id"] == "123456"

    assert customer["preferred_accent"] == "portuguese"

    assert customer["onboarding_completed"] is False


def test_login_sets_session_cookie() -> None:
    client = TestClient(app)

    create_customer(client)

    response = login(client)

    assert response.status_code == 200

    assert "factored_session" in response.cookies


def test_login_with_unknown_factored_id_fails() -> None:
    client = TestClient(app)

    response = login(
        client,
        factored_id="999999",
    )

    assert response.status_code == 401


def test_me_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_returns_authenticated_customer() -> None:
    client = TestClient(app)

    created = create_customer(client)

    login_response = login(client)

    assert login_response.status_code == 200

    response = client.get("/api/auth/me")

    assert response.status_code == 200

    body = response.json()

    assert body["customer_id"] == created["customer_id"]

    assert body["first_name"] == "Gabriel"
    assert body["last_name"] == "Factored"
    assert body["factored_id"] == "123456"

    assert body["preferred_accent"] == "portuguese"

    assert body["onboarding_completed"] is False


def test_logout_invalidates_session() -> None:
    client = TestClient(app)

    create_customer(client)
    login(client)

    before_logout = client.get("/api/auth/me")

    assert before_logout.status_code == 200

    response = client.post("/api/auth/logout")

    assert response.status_code == 200

    assert response.json() == {
        "authenticated": False,
    }

    after_logout = client.get("/api/auth/me")

    assert after_logout.status_code == 401


def test_customer_sessions_are_isolated() -> None:
    first_client = TestClient(app)
    second_client = TestClient(app)

    first = create_customer(
        first_client,
        factored_id="111111",
        first_name="Gabriel",
        phone="+5511981020050",
    )

    second = create_customer(
        second_client,
        factored_id="222222",
        first_name="Jordan",
        phone="+573001234567",
    )

    first_login = login(
        first_client,
        factored_id="111111",
    )

    second_login = login(
        second_client,
        factored_id="222222",
    )

    assert first_login.status_code == 200
    assert second_login.status_code == 200

    first_me = first_client.get("/api/auth/me")

    second_me = second_client.get("/api/auth/me")

    assert first_me.status_code == 200
    assert second_me.status_code == 200

    assert first_me.json()["customer_id"] == first["customer_id"]

    assert second_me.json()["customer_id"] == second["customer_id"]

    assert first_me.json()["customer_id"] != second_me.json()["customer_id"]


def test_onboarding_state_is_customer_specific() -> None:
    first_client = TestClient(app)
    second_client = TestClient(app)

    create_customer(
        first_client,
        factored_id="111111",
        first_name="Gabriel",
        phone="+5511981020050",
    )

    create_customer(
        second_client,
        factored_id="222222",
        first_name="Jordan",
        phone="+573001234567",
    )

    login(
        first_client,
        factored_id="111111",
    )

    login(
        second_client,
        factored_id="222222",
    )

    completion = first_client.patch(
        "/api/onboarding/tour",
        json={"status": "completed", "last_completed_step": "finish"},
    )

    assert completion.status_code == 200

    first_me = first_client.get("/api/auth/me")

    second_me = second_client.get("/api/auth/me")

    assert first_me.json()["onboarding_completed"] is True

    assert second_me.json()["onboarding_completed"] is False


def demo_options(client: TestClient, query: str = "") -> list[dict]:
    response = client.get("/api/auth/demo-customers", params={"q": query})
    assert response.status_code == 200
    return response.json()["options"]


def test_demo_customer_search_ignores_case_and_accents() -> None:
    client = TestClient(app)
    create_customer(
        client,
        factored_id="345678",
        first_name="José María",
        last_name="Pérez López",
        preferred_accent="colombian_spanish",
    )

    options = demo_options(client, "JOSE MARIA PEREZ")

    assert [option["full_name"] for option in options] == ["José María Pérez López"]


def test_demo_options_expose_minimum_information_and_disambiguate_names() -> None:
    client = TestClient(app)
    create_customer(client, factored_id="111111", first_name="Ana", last_name="Silva")
    create_customer(
        client,
        factored_id="222222",
        first_name="Ana",
        last_name="Silva",
        phone="+5511981020060",
    )

    options = demo_options(client, "ana silva")

    assert len(options) == 2
    assert all(set(option) == {"selection", "full_name", "disambiguator"} for option in options)
    assert len({option["disambiguator"] for option in options}) == 2
    assert "111111" not in str(options)
    assert "222222" not in str(options)


def test_demo_selection_logs_in_exact_customer_and_returns_locale() -> None:
    client = TestClient(app)
    expected = create_customer(
        client,
        factored_id="345678",
        first_name="José María",
        last_name="Pérez López",
        preferred_accent="colombian_spanish",
    )
    selection = demo_options(client, "jose maria")[0]["selection"]

    response = client.post("/api/auth/demo-login", json={"selection": selection})

    assert response.status_code == 200
    assert response.json()["customer"]["customer_id"] == expected["customer_id"]
    assert response.json()["customer"]["locale"] == "es-CO"
    assert client.get("/api/auth/me").json()["customer_id"] == expected["customer_id"]


def test_tampered_demo_selection_is_rejected_without_session() -> None:
    client = TestClient(app)
    create_customer(client)
    selection = demo_options(client, "Gabriel")[0]["selection"]

    response = client.post(
        "/api/auth/demo-login",
        json={"selection": f"{selection[:-1]}x"},
    )

    assert response.status_code == 401
    assert "no longer available" in response.json()["detail"]
    assert client.get("/api/auth/me").status_code == 401


def test_stale_and_inactive_demo_selections_are_rejected() -> None:
    stale_client = TestClient(app)
    created = create_customer(stale_client)
    selection = demo_options(stale_client, "Gabriel")[0]["selection"]
    customer = customer_repository.get_by_id(created["customer_id"])
    assert customer is not None
    customer_repository.update(customer.model_copy(update={"customer_status": "Inactive"}))

    assert demo_options(stale_client, "Gabriel") == []
    response = stale_client.post("/api/auth/demo-login", json={"selection": selection})
    assert response.status_code == 401
    assert stale_client.get("/api/auth/me").status_code == 401


def test_malformed_demo_selection_is_rejected() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/auth/demo-login",
        json={"selection": "not-a-valid-selection-token"},
    )

    assert response.status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_demo_login_keeps_customer_sessions_isolated() -> None:
    first_client = TestClient(app)
    second_client = TestClient(app)
    first = create_customer(first_client, factored_id="111111", first_name="First")
    second = create_customer(
        second_client,
        factored_id="222222",
        first_name="Second",
        phone="+5511981020060",
        preferred_accent="english",
    )

    first_selection = demo_options(first_client, "First")[0]["selection"]
    second_selection = demo_options(second_client, "Second")[0]["selection"]
    first_client.post("/api/auth/demo-login", json={"selection": first_selection})
    second_client.post("/api/auth/demo-login", json={"selection": second_selection})

    first_me = first_client.get("/api/auth/me").json()
    second_me = second_client.get("/api/auth/me").json()
    assert first_me["customer_id"] == first["customer_id"]
    assert first_me["locale"] == "pt-BR"
    assert second_me["customer_id"] == second["customer_id"]
    assert second_me["locale"] == "en-US"


def test_login_page_uses_accessible_searchable_demo_selector() -> None:
    client = TestClient(app)

    page = client.get("/login").text
    script = client.get("/static/js/pages/login.js").text

    assert 'role="combobox"' in page
    assert 'role="listbox"' in page
    assert 'role="tablist"' in page
    assert 'data-method="customer"' in page
    assert 'data-method="factored-id"' in page
    assert page.index('data-method="factored-id"') < page.index('data-method="customer"')
    factored_tab = page.split('id="factored-id-method"', 1)[1].split("</button>", 1)[0]
    assert 'aria-selected="true"' in factored_tab
    assert 'id="factored-id"' in page
    assert 'aria-required="true"' in page
    assert 'aria-live="polite"' in page
    assert "Demo access only" in page
    assert "Never use this pattern for real banking access" in page
    assert 'event.key === "ArrowDown"' in script
    assert 'event.key === "ArrowUp"' in script
    assert 'event.key === "Enter"' in script
    assert '"/auth/login"' in script
    assert '"/auth/demo-login"' in script
    assert 'const FACTORED_ID_COOKIE = "factored_id"' in script
    assert "prefillFactoredId();" in script
    assert 'setLoginMethod("factored-id")' in script
    assert "factored:demo-login-metric" in script
