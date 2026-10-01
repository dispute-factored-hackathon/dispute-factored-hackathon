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
) -> dict:
    response = client.post(
        "/api/customers",
        json={
            "first_name": "Gabriel",
            "last_name": "Silveira",
            "date_of_birth": "2000-01-01",
            "gender": "male",
            "mobile_phone": "+5511981020050",
            "preferred_accent": "portuguese",
            "factored_id": factored_id,
        },
    )

    assert response.status_code == 201

    return response.json()


def login(
    client: TestClient,
    factored_id: str = "123456",
) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "factored_id": factored_id,
        },
    )

    assert response.status_code == 200


def setup_function() -> None:
    clear_repositories()


def teardown_function() -> None:
    clear_repositories()


def test_home_page_is_available() -> None:
    client = TestClient(app)

    response = client.get("/home")

    assert response.status_code == 200

    assert "FACTORED BANK" in response.text
    assert "IZZY" in response.text
    assert "Shady Business" in response.text
    assert "+1 661 577 9964" in response.text


def test_home_contains_required_navigation() -> None:
    client = TestClient(app)

    response = client.get("/home")

    assert response.status_code == 200

    expected_links = (
        'href="/cards"',
        'href="/transactions"',
        'href="/complaints"',
        'href="/profile"',
        'href="/agent"',
        'href="/shop"',
        'href="tel:+16615779964"',
    )

    for expected_link in expected_links:
        assert expected_link in response.text


def test_home_contains_replay_tutorial() -> None:
    client = TestClient(app)

    response = client.get("/home")

    assert response.status_code == 200

    assert 'href="/onboarding?replay=true"' in response.text

    assert "Replay tutorial" in response.text


def test_authenticated_customer_context() -> None:
    client = TestClient(app)

    created = create_customer(client)
    login(client)

    response = client.get("/api/auth/me")

    assert response.status_code == 200

    body = response.json()

    assert body["customer_id"] == created["customer_id"]

    assert body["first_name"] == "Gabriel"

    assert body["onboarding_completed"] is False


def test_cards_route_uses_real_cards_page() -> None:
    client = TestClient(app)

    response = client.get("/cards")

    assert response.status_code == 200

    assert "Manage your Factored Bank cards" in response.text

    assert "cards.js" in response.text
    assert "Coming soon" not in response.text


def test_transactions_route_uses_real_page() -> None:
    client = TestClient(app)

    response = client.get("/transactions")

    assert response.status_code == 200

    assert "Transaction history" in response.text

    assert "transactions.js" in response.text
    assert "Coming soon" not in response.text


def test_complaints_route_uses_real_page() -> None:
    client = TestClient(app)

    response = client.get("/complaints")

    assert response.status_code == 200

    assert "Complaint history" in response.text

    assert "complaints.js" in response.text
    assert "Coming soon" not in response.text


def test_onboarding_route_is_available() -> None:
    client = TestClient(app)

    response = client.get("/onboarding")

    assert response.status_code == 200

    assert "onboarding.js" in response.text


def test_agent_placeholder_route_is_available() -> None:
    client = TestClient(app)

    response = client.get("/agent")

    assert response.status_code == 200
    assert "Coming soon" in response.text


def test_api_me_remains_protected() -> None:
    client = TestClient(app)

    response = client.get("/api/auth/me")

    assert response.status_code == 401
