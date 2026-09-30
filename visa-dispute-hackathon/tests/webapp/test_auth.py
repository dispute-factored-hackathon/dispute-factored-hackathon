from datetime import date

from fastapi.testclient import TestClient

from webapp.backend.main import app
from webapp.backend.repositories.mock import (
    customer_repository,
    product_repository,
    session_repository,
    transaction_repository,
)

client = TestClient(app)


def clear_repositories() -> None:
    customer_repository._customers.clear()
    product_repository._products.clear()
    transaction_repository._transactions.clear()
    session_repository._sessions.clear()


def create_customer(
    *,
    factored_id: str = "123456",
    first_name: str = "Gabriel",
) -> dict:
    response = client.post(
        "/api/customers",
        json={
            "first_name": first_name,
            "last_name": "Silveira",
            "date_of_birth": str(date(2000, 1, 1)),
            "gender": "male",
            "mobile_phone": "+5511981020050",
            "preferred_accent": "portuguese",
            "factored_id": factored_id,
        },
    )

    assert response.status_code == 201

    return response.json()


def setup_function() -> None:
    clear_repositories()


def teardown_function() -> None:
    clear_repositories()


def test_login_with_valid_factored_id() -> None:
    created = create_customer()

    response = client.post(
        "/api/auth/login",
        json={
            "factored_id": "123456",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["authenticated"] is True
    assert body["customer"]["customer_id"] == created["customer_id"]
    assert body["customer"]["first_name"] == "Gabriel"

    assert "factored_session" in response.cookies


def test_login_rejects_unknown_factored_id() -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "factored_id": "999999",
        },
    )

    assert response.status_code == 401


def test_me_requires_authentication() -> None:
    isolated_client = TestClient(app)

    response = isolated_client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_returns_authenticated_customer() -> None:
    create_customer()

    login_response = client.post(
        "/api/auth/login",
        json={
            "factored_id": "123456",
        },
    )

    assert login_response.status_code == 200

    response = client.get("/api/auth/me")

    assert response.status_code == 200

    body = response.json()

    assert body["first_name"] == "Gabriel"
    assert body["last_name"] == "Silveira"


def test_logout_invalidates_session() -> None:
    create_customer()

    login_response = client.post(
        "/api/auth/login",
        json={
            "factored_id": "123456",
        },
    )

    assert login_response.status_code == 200

    before_logout = client.get("/api/auth/me")

    assert before_logout.status_code == 200

    logout_response = client.post("/api/auth/logout")

    assert logout_response.status_code == 200

    assert logout_response.json()["authenticated"] is False

    after_logout = client.get("/api/auth/me")

    assert after_logout.status_code == 401


def test_sessions_keep_customers_isolated() -> None:
    first = create_customer(
        factored_id="111111",
        first_name="Gabriel",
    )

    second_response = client.post(
        "/api/customers",
        json={
            "first_name": "Jordan",
            "last_name": "Factored",
            "date_of_birth": "1995-01-01",
            "gender": "male",
            "mobile_phone": "+573001234567",
            "preferred_accent": "colombian_spanish",
            "factored_id": "222222",
        },
    )

    assert second_response.status_code == 201

    second = second_response.json()

    first_client = TestClient(app)
    second_client = TestClient(app)

    first_login = first_client.post(
        "/api/auth/login",
        json={
            "factored_id": "111111",
        },
    )

    second_login = second_client.post(
        "/api/auth/login",
        json={
            "factored_id": "222222",
        },
    )

    assert first_login.status_code == 200
    assert second_login.status_code == 200

    first_me = first_client.get("/api/auth/me").json()

    second_me = second_client.get("/api/auth/me").json()

    assert first_me["customer_id"] == first["customer_id"]

    assert second_me["customer_id"] == second["customer_id"]

    assert first_me["customer_id"] != second_me["customer_id"]
