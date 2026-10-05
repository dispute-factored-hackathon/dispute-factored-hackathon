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


def test_contextual_tour_is_interactive_and_handles_empty_accounts() -> None:
    client = TestClient(app)
    response = client.get("/static/js/components/guided-tour.js")

    assert response.status_code == 200
    content = response.text
    for expected in (
        'id: "cards-link"',
        'target: ".bank-card.is-active"',
        'id: "transactions"',
        'id: "izzy"',
        "target: \"[data-tour='izzy']\"",
        'id: "complaints-link"',
        'target: ".complaint-item, #empty-state"',
        'id: "profile-link"',
        'id: "finish"',
        'action: "activate"',
        "element.addEventListener",
        "guided-tour-no-target",
    ):
        assert expected in content
    assert "pt:" not in content
    assert "es:" not in content
    assert 'id: "report-transaction"' not in content
    assert "transactionDetailRoute" not in content
    assert 'id: "complaint-detail"' not in content
    assert 'target: ".complaint-item"' not in content
    transactions_step = content.split('id: "transactions"', 1)[1].split("},", 1)[0]
    assert "target:" not in transactions_step
    profile_link_step = content.split('id: "profile-link"', 1)[1].split("},", 1)[0]
    assert "target:" not in profile_link_step
    assert "action:" not in profile_link_step
    finish_step = content.split('id: "finish"', 1)[1].split("},", 1)[0]
    assert "target:" not in finish_step
    assert "action:" not in finish_step


def test_empty_transaction_history_has_truthful_tour_copy() -> None:
    client = TestClient(app)
    create_customer(client)
    login(client)
    transaction_repository._transactions.clear()

    assert client.get("/api/transactions").json() == []
    javascript = client.get("/static/js/components/guided-tour.js").text
    assert "document.querySelectorAll(selector)" in javascript
    assert 'route: "/home",\n        target: "[data-tour=\'izzy\']"' in javascript

    expected_copy = {
        "en": ("no purchases yet", "no transactions yet", "no complaints yet"),
        "pt": ("ainda não tem compras", "nenhuma transação ainda", "nenhuma contestação ainda"),
        "es": ("todavía no tiene compras", "aún no hay transacciones", "aún no hay reclamos"),
    }
    for language, phrases in expected_copy.items():
        catalog = client.get(f"/static/locales/v1/{language}.json").json()
        combined = " ".join(
            (
                catalog["tour.welcome_body"],
                catalog["tour.transactions_link_body"],
                catalog["tour.transactions_title"],
                catalog["tour.transactions_body"],
                catalog["tour.complaints_title"],
                catalog["tour.complaints_body"],
                catalog["tour.finish_body"],
            )
        ).lower()
        assert all(phrase in combined for phrase in phrases)
        assert "shady business" in combined


def test_first_tour_completion_prompts_shady_business_after_overlay_closes() -> None:
    client = TestClient(app)
    javascript = client.get("/static/js/components/guided-tour.js").text
    home_javascript = client.get("/static/js/pages/home.js").text
    home = client.get("/home").text
    css = client.get("/static/css/pages/home.css").text

    assert 'const FIRST_EXPERIENCE = "first-experience"' in javascript
    assert 'CustomEvent("factored:shady-start")' in javascript
    assert 'last_completed_step: "shady-business-started"' in home_javascript
    assert 'state.last_completed_step === "finish"' in home_javascript
    assert 'id="shady-start-hint"' in home
    assert "Start here" in home
    assert ".shady-business-start" in css
    assert ".shady-start-hint[hidden]" in css
    assert "prefers-reduced-motion" in css


def test_replayed_tour_does_not_restore_first_login_store_prompt() -> None:
    client = TestClient(app)
    javascript = client.get("/static/js/components/guided-tour.js").text

    assert 'const completedStep = mode === REPLAY ? "replay-finish"' in javascript
    assert "mode === FIRST_EXPERIENCE" in javascript


def test_shady_business_prompt_state_is_accepted_and_persisted() -> None:
    client = TestClient(app)
    created = create_customer(client)
    login(client)

    finished = client.patch(
        "/api/onboarding/tour",
        json={"status": "completed", "last_completed_step": "finish"},
    )
    started = client.patch(
        "/api/onboarding/tour",
        json={"status": "completed", "last_completed_step": "shady-business-started"},
    )

    assert finished.status_code == 200
    assert started.status_code == 200
    assert started.json()["last_completed_step"] == "shady-business-started"
    stored = customer_repository.get_by_id(created["customer_id"])
    assert stored is not None
    assert stored.tutorial_last_completed_step == "shady-business-started"


def test_start_here_copy_exists_in_all_supported_languages() -> None:
    client = TestClient(app)
    expected = {
        "en": "Start here",
        "pt": "Comece por aqui",
        "es": "Comienza aquí",
    }
    for language, copy in expected.items():
        catalog = client.get(f"/static/locales/v1/{language}.json").json()
        assert catalog["home.start_here"] == copy


def test_empty_complaint_history_does_not_block_contextual_tour() -> None:
    client = TestClient(app)
    create_customer(client)
    login(client)
    complaint_repository._complaints.clear()

    assert client.get("/api/complaints").json() == []
    javascript = client.get("/static/js/components/guided-tour.js").text
    assert 'id: "complaints"' in javascript
    assert 'target: ".complaint-item, #empty-state"' in javascript
    assert 'id: "complaint-detail"' not in javascript
    assert 'target: ".complaint-item"' not in javascript

    progress = client.patch(
        "/api/onboarding/tour",
        json={"status": "in_progress", "last_completed_step": "complaints"},
    )
    assert progress.status_code == 200
    assert progress.json()["last_completed_step"] == "complaints"


def test_demo_selector_login_does_not_offer_or_update_tutorial() -> None:
    client = TestClient(app)
    create_customer(client)
    selection = client.get("/api/auth/demo-customers", params={"q": "Gabriel"}).json()["options"][
        0
    ]["selection"]
    login_response = client.post("/api/auth/demo-login", json={"selection": selection})

    assert login_response.status_code == 200
    assert login_response.json()["customer"]["onboarding_eligible"] is False
    assert client.get("/api/onboarding/tour").json() == {
        "version": 4,
        "status": "not_started",
        "last_completed_step": None,
        "should_offer": False,
        "eligible": False,
    }
    response = client.patch(
        "/api/onboarding/tour",
        json={"status": "in_progress", "last_completed_step": None},
    )
    assert response.status_code == 403


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


def test_complaint_details_resume_the_contextual_tour() -> None:
    client = TestClient(app)
    content = client.get("/static/js/pages/complaint-detail.js").text

    assert 'from "../components/guided-tour.js?v=11"' in content
    assert "await initializeGuidedTour();" in content


def test_pages_load_the_cache_busted_empty_account_tour() -> None:
    client = TestClient(app)
    expected_version = "v=20261005-onboarding-empty3"

    for page in (
        "home",
        "cards",
        "transactions",
        "agent",
        "complaints",
        "profile",
        "transaction-detail",
        "complaint-detail",
        "coming-soon",
    ):
        html = client.get(f"/static/pages/{page}.html").text
        assert expected_version in html


def test_contextual_tour_keeps_targets_visible_clickable_and_non_overlapping() -> None:
    client = TestClient(app)
    css = client.get("/static/css/components.css").text
    javascript = client.get("/static/js/components/guided-tour.js").text

    assert ".guided-tour-target" in css
    assert ".guided-tour-target-action" in css
    assert "guided-tour-click-target" in css
    assert '"guided-tour-target-action", requiresTargetActivation(step)' in javascript
    assert "z-index: 102" in css
    assert "pointer-events: none" in css
    assert "tooltipPlacement" in javascript
    assert "window.innerWidth" in javascript
    assert "window.innerHeight" in javascript
    assert "prefers-reduced-motion" in css


def test_click_targets_are_distinct_from_informational_highlights() -> None:
    client = TestClient(app)
    css = client.get("/static/css/components.css").text
    javascript = client.get("/static/js/components/guided-tour.js").text

    assert "outline-color: #ffcf5c" in css
    assert "animation: guided-tour-click-target" in css
    assert 'target.classList.toggle("guided-tour-target-action"' in javascript
    for language in ("en", "pt", "es"):
        instruction = client.get(f"/static/locales/v1/{language}.json").json()["tour.activate"]
        assert any(color in instruction.lower() for color in ("gold", "dourado", "dorado"))


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
