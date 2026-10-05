from fakes import (
    complaint_repository,
    customer_repository,
    product_repository,
    session_repository,
    transaction_repository,
)
from fastapi.testclient import TestClient

from webapp.backend.main import app


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

    response = client.get("/onboarding", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
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
        "version": 4,
        "status": "not_started",
        "last_completed_step": None,
        "should_offer": True,
        "eligible": True,
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
    assert stored.tutorial_version == 4
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
        "version": 4,
        "status": "not_started",
        "last_completed_step": None,
        "should_offer": True,
        "eligible": True,
    }


def test_contextual_tour_is_interactive_and_english_only() -> None:
    client = TestClient(app)
    response = client.get("/static/js/components/guided-tour.js")

    assert response.status_code == 200
    content = response.text
    for expected in (
        'id: "cards-link"',
        'target: ".bank-card.is-active"',
        'id: "transactions"',
        'id: "izzy"',
        'id: "complaints-link"',
        'target: ".page-heading"',
        'id: "profile-link"',
        "target: \"[data-tour='shady-business']\"",
        'id: "finish"',
        'action: "finish-and-activate"',
        'action: "activate"',
        "element.addEventListener",
        "guided-tour-no-target",
    ):
        assert expected in content
    assert "pt:" not in content
    assert "es:" not in content
    assert 'id: "complaint-detail"' not in content
    assert 'target: ".complaint-item"' not in content
    assert 'target: ".transaction-item"' not in content
    assert 'id: "report-transaction"' not in content


def test_first_tour_step_highlights_shady_business_as_the_start() -> None:
    client = TestClient(app)
    javascript = client.get("/static/js/components/guided-tour.js").text
    english = client.get("/static/locales/v1/en.json").json()
    portuguese = client.get("/static/locales/v1/pt.json").json()
    spanish = client.get("/static/locales/v1/es.json").json()

    welcome_step = javascript.split('id: "welcome"', 1)[1].split("},", 1)[0]
    assert "target: \"[data-tour='shady-business']\"" in welcome_step
    assert 'target.matches(".shady-business")' in javascript
    assert english["tour.welcome_title"] == "Your experience starts at Shady Business"
    assert portuguese["tour.welcome_title"] == "Sua experiência começa na Shady Business"
    assert spanish["tour.welcome_title"] == "Tu experiencia comienza en Shady Business"


def test_empty_transaction_history_does_not_ask_customer_to_pick_one() -> None:
    client = TestClient(app)
    create_customer(client)
    login(client)
    transaction_repository._transactions.clear()

    assert client.get("/api/transactions").json() == []
    javascript = client.get("/static/js/components/guided-tour.js").text
    english = client.get("/static/locales/v1/en.json").json()

    assert 'id: "transactions"' in javascript
    assert 'target: ".transaction-item"' not in javascript
    assert 'id: "report-transaction"' not in javascript
    assert english["tour.transactions_title"] == "Your transaction history starts here"
    assert "begin with no transactions" in english["tour.transactions_body"]


def test_empty_complaint_history_does_not_block_contextual_tour() -> None:
    client = TestClient(app)
    create_customer(client)
    login(client)
    complaint_repository._complaints.clear()

    assert client.get("/api/complaints").json() == []
    javascript = client.get("/static/js/components/guided-tour.js").text
    assert 'id: "complaints"' in javascript
    assert 'target: ".page-heading"' in javascript
    assert 'id: "complaint-detail"' not in javascript
    assert 'target: ".complaint-item"' not in javascript

    progress = client.patch(
        "/api/onboarding/tour",
        json={"status": "in_progress", "last_completed_step": "complaints"},
    )
    assert progress.status_code == 200
    assert progress.json()["last_completed_step"] == "complaints"


def test_demo_selector_login_offers_and_updates_tutorial() -> None:
    client = TestClient(app)
    create_customer(client)
    selection = client.get("/api/auth/demo-customers", params={"q": "Gabriel"}).json()["options"][
        0
    ]["selection"]
    login_response = client.post("/api/auth/demo-login", json={"selection": selection})

    assert login_response.status_code == 200
    assert login_response.json()["customer"]["onboarding_eligible"] is True
    assert client.get("/api/auth/me").json()["onboarding_eligible"] is True
    assert "Replay tutorial" in client.get("/home").text
    assert client.get("/api/onboarding/tour").json() == {
        "version": 4,
        "status": "not_started",
        "last_completed_step": None,
        "should_offer": True,
        "eligible": True,
    }
    response = client.patch(
        "/api/onboarding/tour",
        json={"status": "in_progress", "last_completed_step": None},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


def test_tour_script_retries_transient_progress_failures_and_keeps_mobile_controls_visible() -> (
    None
):
    client = TestClient(app)
    javascript = client.get("/static/js/components/guided-tour.js").text
    css = client.get("/static/css/components.css").text

    assert "const SAVE_ATTEMPTS = 3" in javascript
    assert "window.visualViewport" in javascript
    assert "positionMobileTooltip" in javascript
    assert ".guided-tour-content" in css
    assert "overflow-y: auto" in css
    assert "flex: 0 0 auto" in css
    assert "100dvh" in css


def test_active_card_step_reserves_readable_space_on_short_mobile_screens() -> None:
    client = TestClient(app)
    javascript = client.get("/static/js/components/guided-tour.js").text
    css = client.get("/static/css/components.css").text

    assert 'mobilePlacement: "above"' in javascript
    assert 'layer.dataset.step = step.id' in javascript
    assert 'block: viewportSize().width <= MOBILE_BREAKPOINT ? mobileBlock : "center"' in javascript
    assert '@media (max-width: 600px) and (max-height: 700px)' in css
    assert '.guided-tour[data-step="cards"] .guided-tour-tooltip' in css
    assert 'grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)' in css


def test_mobile_click_steps_separate_explanation_from_target_selection() -> None:
    client = TestClient(app)
    javascript = client.get("/static/js/components/guided-tour.js").text
    css = client.get("/static/css/components.css").text

    assert 'let mobilePresentation = "explanation"' in javascript
    assert "usesSplitMobilePresentation" in javascript
    assert 'mobilePresentation === "target"' in javascript
    assert 'mobilePresentation = "target"' in javascript
    assert 'layer.dataset.presentation = mobileTargetPresentation ? "target" : "explanation"' in (
        javascript
    )
    assert 'emitMetric("mobile_target_prompted")' in javascript
    assert 'tooltip.setAttribute("aria-label", t(COPY.controls.activate))' in javascript
    assert 'tooltip.setAttribute("aria-labelledby", "guided-tour-title")' in javascript
    assert ".guided-tour-mobile-target-phase .guided-tour-content" in css
    assert "display: none" in css
    assert ".guided-tour-mobile-target-phase .guided-tour-actions" in css


def test_complaint_details_resume_the_contextual_tour() -> None:
    client = TestClient(app)
    content = client.get("/static/js/pages/complaint-detail.js").text

    assert 'from "../components/guided-tour.js?v=11"' in content
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


def test_clickable_tour_cards_use_an_accessible_attention_animation() -> None:
    client = TestClient(app)
    css = client.get("/static/css/components.css").text
    javascript = client.get("/static/js/components/guided-tour.js").text

    assert 'target.matches(".hub-card, .bank-card")' in javascript
    assert '"guided-tour-target-attention"' in javascript
    assert ".guided-tour-target-attention::before" in css
    assert "@keyframes guided-tour-card-attention" in css
    assert "@keyframes guided-tour-card-icon-attention" in css
    assert "pointer-events: none" in css
    assert "prefers-reduced-motion: reduce" in css


def test_contextual_tour_reenables_controls_after_changing_steps() -> None:
    client = TestClient(app)
    content = client.get("/static/js/components/guided-tour.js").text
    show_step = content.split("async function showCurrentStep()", 1)[1]
    show_step = show_step.split("async function activateTarget", 1)[0]

    assert "setControlsDisabled(false);" in show_step


def test_cards_render_an_explicit_active_tour_target() -> None:
    client = TestClient(app)
    content = client.get("/static/js/pages/cards.js?v=2").text

    assert '"bank-card is-active"' in content
