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
    mobile_phone: str = "+5511981020050",
) -> dict:
    response = client.post(
        "/api/customers",
        json={
            "first_name": "Gabriel",
            "last_name": "Factored",
            "date_of_birth": "2000-01-01",
            "gender": "male",
            "mobile_phone": mobile_phone,
            "preferred_accent": "portuguese",
            "factored_id": factored_id,
        },
    )

    assert response.status_code == 201

    return response.json()


def login(
    client: TestClient,
    factored_id: str = "123456",
) -> dict:
    response = client.post(
        "/api/auth/login",
        json={
            "factored_id": factored_id,
        },
    )

    assert response.status_code == 200

    return response.json()


def setup_function() -> None:
    clear_repositories()


def teardown_function() -> None:
    clear_repositories()


def test_onboarding_page_is_available() -> None:
    client = TestClient(app)

    response = client.get("/onboarding")

    assert response.status_code == 200

    assert "Learn how to use the Factored Bank demo" in response.text

    assert "onboarding.js" in response.text


def test_onboarding_page_contains_controls() -> None:
    client = TestClient(app)

    response = client.get("/onboarding")

    assert response.status_code == 200

    assert 'id="skip-button"' in response.text

    assert 'id="previous-button"' in response.text

    assert 'id="next-button"' in response.text


def test_onboarding_state_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/onboarding")

    assert response.status_code == 401


def test_complete_onboarding_requires_authentication() -> None:
    client = TestClient(app)

    response = client.post("/api/onboarding/complete")

    assert response.status_code == 401


def test_new_customer_has_incomplete_onboarding() -> None:
    client = TestClient(app)

    create_customer(client)
    login(client)

    response = client.get("/api/onboarding")

    assert response.status_code == 200

    assert response.json() == {
        "onboarding_completed": False,
    }


def test_login_exposes_incomplete_onboarding() -> None:
    client = TestClient(app)

    create_customer(client)

    response = login(client)

    assert response["customer"]["onboarding_completed"] is False


def test_auth_me_exposes_onboarding_state() -> None:
    client = TestClient(app)

    create_customer(client)
    login(client)

    response = client.get("/api/auth/me")

    assert response.status_code == 200

    customer = response.json()

    assert customer["onboarding_completed"] is False


def test_auth_me_exposes_factored_id() -> None:
    client = TestClient(app)

    create_customer(
        client,
        factored_id="654321",
    )

    login(
        client,
        "654321",
    )

    response = client.get("/api/auth/me")

    assert response.status_code == 200

    assert response.json()["factored_id"] == "654321"


def test_customer_can_complete_onboarding() -> None:
    client = TestClient(app)

    create_customer(client)
    login(client)

    response = client.post("/api/onboarding/complete")

    assert response.status_code == 200

    assert response.json() == {
        "onboarding_completed": True,
    }


def test_completion_updates_onboarding_state() -> None:
    client = TestClient(app)

    create_customer(client)
    login(client)

    client.post("/api/onboarding/complete")

    response = client.get("/api/onboarding")

    assert response.status_code == 200

    assert response.json() == {
        "onboarding_completed": True,
    }


def test_completion_updates_customer_repository() -> None:
    client = TestClient(app)

    created = create_customer(client)
    login(client)

    response = client.post("/api/onboarding/complete")

    assert response.status_code == 200

    customer = customer_repository.get_by_id(created["customer_id"])

    assert customer is not None

    assert customer.onboarding_completed is True


def test_auth_me_reflects_completed_onboarding() -> None:
    client = TestClient(app)

    create_customer(client)
    login(client)

    client.post("/api/onboarding/complete")

    response = client.get("/api/auth/me")

    assert response.status_code == 200

    assert response.json()["onboarding_completed"] is True


def test_completing_onboarding_is_idempotent() -> None:
    client = TestClient(app)

    create_customer(client)
    login(client)

    first = client.post("/api/onboarding/complete")

    second = client.post("/api/onboarding/complete")

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json() == {
        "onboarding_completed": True,
    }

    assert second.json() == {
        "onboarding_completed": True,
    }

    tour = client.get("/api/onboarding/tour").json()
    assert tour["status"] == "completed"
    assert tour["last_completed_step"] == "replay"


def test_home_contains_replay_tutorial_link() -> None:
    client = TestClient(app)

    response = client.get("/home")

    assert response.status_code == 200

    assert 'href="/home?tour=start"' in response.text

    assert "Replay tutorial" in response.text


def test_tutorial_state_requires_authentication() -> None:
    client = TestClient(app)

    assert client.get("/api/onboarding/tour").status_code == 401
    assert (
        client.patch(
            "/api/onboarding/tour",
            json={"status": "in_progress", "last_completed_step": None},
        ).status_code
        == 401
    )


def test_new_customer_is_offered_contextual_tour() -> None:
    client = TestClient(app)
    create_customer(client)
    login(client)

    response = client.get("/api/onboarding/tour")

    assert response.status_code == 200
    assert response.json() == {
        "version": 1,
        "status": "not_started",
        "last_completed_step": None,
        "should_offer": True,
    }


def test_tutorial_progress_is_persisted_for_customer() -> None:
    client = TestClient(app)
    created = create_customer(client)
    login(client)

    response = client.patch(
        "/api/onboarding/tour",
        json={"status": "in_progress", "last_completed_step": "cards"},
    )

    assert response.status_code == 200
    assert response.json()["last_completed_step"] == "cards"
    stored = customer_repository.get_by_id(created["customer_id"])
    assert stored is not None
    assert stored.tutorial_version == 1
    assert stored.tutorial_status == "in_progress"
    assert stored.tutorial_last_completed_step == "cards"


def test_completing_contextual_tour_marks_onboarding_complete() -> None:
    client = TestClient(app)
    created = create_customer(client)
    login(client)

    response = client.patch(
        "/api/onboarding/tour",
        json={"status": "completed", "last_completed_step": "replay"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["should_offer"] is False
    stored = customer_repository.get_by_id(created["customer_id"])
    assert stored is not None
    assert stored.onboarding_completed is True


def test_skipping_contextual_tour_is_remembered() -> None:
    client = TestClient(app)
    create_customer(client)
    login(client)

    client.patch(
        "/api/onboarding/tour",
        json={"status": "skipped", "last_completed_step": "menu"},
    )
    response = client.get("/api/onboarding/tour")

    assert response.json()["status"] == "skipped"
    assert response.json()["last_completed_step"] == "menu"
    assert response.json()["should_offer"] is False


def test_tutorial_rejects_unknown_step() -> None:
    client = TestClient(app)
    create_customer(client)
    login(client)

    response = client.patch(
        "/api/onboarding/tour",
        json={"status": "in_progress", "last_completed_step": "not-a-step"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown tutorial step."


def test_tutorial_progress_is_isolated_between_customers() -> None:
    first = TestClient(app)
    second = TestClient(app)
    create_customer(first, factored_id="123456")
    create_customer(
        second,
        factored_id="654321",
        mobile_phone="+5511981020060",
    )
    first.post("/api/auth/login", json={"factored_id": "123456"})
    second.post("/api/auth/login", json={"factored_id": "654321"})

    first.patch(
        "/api/onboarding/tour",
        json={"status": "in_progress", "last_completed_step": "cards-link"},
    )

    assert first.get("/api/onboarding/tour").json()["last_completed_step"] == "cards-link"
    assert second.get("/api/onboarding/tour").json()["last_completed_step"] is None


def test_new_tutorial_version_is_offered_again() -> None:
    client = TestClient(app)
    created = create_customer(client)
    login(client)
    customer = customer_repository.get_by_id(created["customer_id"])
    assert customer is not None
    customer_repository.update(
        customer.model_copy(
            update={
                "tutorial_version": 999,
                "tutorial_status": "completed",
                "tutorial_last_completed_step": "replay",
            }
        )
    )

    state = client.get("/api/onboarding/tour").json()

    assert state == {
        "version": 1,
        "status": "not_started",
        "last_completed_step": None,
        "should_offer": True,
    }


def test_contextual_tour_component_covers_required_journey_and_languages() -> None:
    client = TestClient(app)

    response = client.get("/static/js/components/guided-tour.js")

    assert response.status_code == 200
    content = response.text
    for expected in (
        'id: "menu"',
        'id: "cards"',
        'id: "transactions"',
        'id: "report-transaction"',
        'id: "izzy"',
        'id: "complaints"',
        'id: "profile"',
        'id: "replay"',
        "pt:",
        "es:",
        "prefers-reduced-motion",
    ):
        assert expected in content or expected in client.get("/static/css/components.css").text


def test_onboarding_contains_mobile_phone_action() -> None:
    client = TestClient(app)

    response = client.get("/static/js/pages/onboarding.js")

    assert response.status_code == 200

    assert "tel:${IZZY_PHONE}" in response.text

    assert "+1 661 577 9964" in response.text


def test_onboarding_mentions_factored_id() -> None:
    client = TestClient(app)

    response = client.get("/static/js/pages/onboarding.js")

    assert response.status_code == 200

    assert "YOUR FACTORED ID" in response.text

    assert "telephone keypad" in response.text


def test_onboarding_covers_demo_journey() -> None:
    client = TestClient(app)

    response = client.get("/static/js/pages/onboarding.js")

    assert response.status_code == 200

    content = response.text

    expected_content = (
        "Factored Bank demo",
        "demo bank account",
        "credit card",
        "Shady Business",
        "bank transactions",
        "suspicious",
        "TRANSACTIONS",
        "Report this transaction",
        "MEET IZZY",
        "CALL IZZY",
        "TELEPHONE AUTHENTICATION",
        "YOUR DISPUTES",
    )

    for expected in expected_content:
        assert expected in content
