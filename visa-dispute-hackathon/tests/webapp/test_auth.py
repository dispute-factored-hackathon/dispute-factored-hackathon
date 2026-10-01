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
) -> dict:
    response = client.post(
        "/api/customers",
        json={
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": "2000-01-01",
            "gender": "male",
            "mobile_phone": phone,
            "preferred_accent": "portuguese",
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
