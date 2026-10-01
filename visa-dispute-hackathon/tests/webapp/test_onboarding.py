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


def login(client: TestClient, factored_id: str = "123456") -> dict:
    response = client.post("/api/auth/login", json={"factored_id": factored_id})
    assert response.status_code == 200
    return response.json()


def setup_function() -> None:
    clear_repositories()


def teardown_function() -> None:
    clear_repositories()


def test_legacy_onboarding_experience_is_removed() -> None:
    client = TestClient(app)

    assert client.get("/onboarding").status_code == 404
    assert client.get("/static/js/pages/onboarding.js").status_code == 404
    assert client.get("/static/css/pages/onboarding.css").status_code == 404
    assert client.get("/api/onboarding").status_code == 404
    assert client.post("/api/onboarding/complete").status_code == 404


def test_login_and_auth_me_expose_tutorial_completion_state() -> None:
    client = TestClient(app)
    create_customer(client)

    assert login(client)["customer"]["onboarding_completed"] is False
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["onboarding_completed"] is False


def test_home_contains_contextual_tour_replay_link() -> None:
    client = TestClient(app)
    response = client.get("/home")

    assert response.status_code == 200
    assert 'href="/home?tour=start"' in response.text
    assert "Replay tutorial" in response.text


def test_home_exposes_interactive_tour_targets() -> None:
    client = TestClient(app)
    response = client.get("/home")

    assert response.status_code == 200
    for target in (
        'data-tour="cards-link"',
        'data-tour="transactions-link"',
        'data-tour="complaints-link"',
        'data-tour="profile-link"',
    ):
        assert target in response.text


def test_tutorial_state_requires_authentication() -> None:
    client = TestClient(app)

    assert client.get("/api/onboarding/tour").status_code == 401
    response = client.patch(
        "/api/onboarding/tour",
        json={"status": "in_progress", "last_completed_step": None},
    )
    assert response.status_code == 401


def test_new_customer_is_offered_contextual_tour() -> None:
    client = TestClient(app)
    create_customer(client)
    login(client)

    response = client.get("/api/onboarding/tour")

    assert response.status_code == 200
    assert response.json() == {
        "version": 3,
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
    assert stored.tutorial_version == 3
    assert stored.tutorial_status == "in_progress"
    assert stored.tutorial_last_completed_step == "cards"


def test_completing_contextual_tour_marks_onboarding_complete() -> None:
    client = TestClient(app)
    created = create_customer(client)
    login(client)

    response = client.patch(
        "/api/onboarding/tour",
        json={"status": "completed", "last_completed_step": "finish"},
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
        json={"status": "skipped", "last_completed_step": "cards-link"},
    )
    response = client.get("/api/onboarding/tour")

    assert response.json()["status"] == "skipped"
    assert response.json()["last_completed_step"] == "cards-link"
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
    login(first, "123456")
    login(second, "654321")

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
                "tutorial_version": 1,
                "tutorial_status": "completed",
                "tutorial_last_completed_step": "replay",
            }
        )
    )

    assert client.get("/api/onboarding/tour").json() == {
        "version": 3,
        "status": "not_started",
        "last_completed_step": None,
        "should_offer": True,
    }


def test_contextual_tour_is_interactive_and_english_only() -> None:
    client = TestClient(app)
    response = client.get("/static/js/components/guided-tour.js")

    assert response.status_code == 200
    content = response.text
    for expected in (
        'id: "cards-link"',
        'id: "transactions"',
        'id: "report-transaction"',
        'id: "izzy"',
        'id: "complaints-link"',
        'id: "complaint-detail"',
        'id: "profile-link"',
        'id: "shady-business"',
        "target: \"[data-tour='shady-business']\"",
        'id: "finish"',
        'action: "activate"',
        'actionTarget: "#report-button"',
        'actionTarget: ".complaint-item"',
        "element.addEventListener",
        "guided-tour-no-target",
    ):
        assert expected in content
    assert "pt:" not in content
    assert "es:" not in content


def test_complaint_details_resume_the_contextual_tour() -> None:
    client = TestClient(app)
    content = client.get("/static/js/pages/complaint-detail.js").text

    assert 'from "../components/guided-tour.js"' in content
    assert "await initializeGuidedTour();" in content


def test_contextual_tour_keeps_targets_visible_clickable_and_non_overlapping() -> None:
    client = TestClient(app)
    css = client.get("/static/css/components.css").text
    javascript = client.get("/static/js/components/guided-tour.js").text

    assert ".guided-tour-target" in css
    assert "z-index: 102" in css
    assert "pointer-events: none" in css
    assert "tooltipPlacement" in javascript
    assert "window.innerWidth" in javascript
    assert "window.innerHeight" in javascript
    assert "prefers-reduced-motion" in css


def test_contextual_tour_reenables_controls_after_changing_steps() -> None:
    client = TestClient(app)
    content = client.get("/static/js/components/guided-tour.js").text
    show_step = content.split("async function showCurrentStep()", 1)[1]
    show_step = show_step.split("async function activateTarget", 1)[0]

    assert "setControlsDisabled(false);" in show_step
