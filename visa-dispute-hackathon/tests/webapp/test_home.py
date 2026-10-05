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


def test_pages_use_product_specific_favicons() -> None:
    client = TestClient(app)
    bank_icon = (
        '<link rel="icon" type="image/svg+xml" href="/static/assets/favicons/factored-bank.svg">'
    )
    store_icon = (
        '<link rel="icon" type="image/svg+xml" href="/static/assets/favicons/shady-business.svg">'
    )

    for route in (
        "/login",
        "/signup",
        "/home",
        "/cards",
        "/transactions",
        "/transactions/example",
        "/complaints",
        "/complaints/example",
        "/profile",
        "/agent",
    ):
        assert bank_icon in client.get(route).text

    for route in (
        "/shop",
        "/shop/products/example",
        "/shop/cart",
    ):
        assert store_icon in client.get(route).text

    assert (
        client.get("/static/assets/favicons/factored-bank.svg").headers["content-type"]
        == "image/svg+xml"
    )
    assert (
        client.get("/static/assets/favicons/shady-business.svg").headers["content-type"]
        == "image/svg+xml"
    )


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


def test_navigation_uses_consistent_svg_icons_and_transactions_label() -> None:
    client = TestClient(app)

    home = client.get("/home").text
    navigation = client.get("/static/js/components/bottom-nav.js").text

    assert home.count('<svg viewBox="0 0 24 24"') >= 4
    assert '<circle cx="12" cy="12" r="9">' in home
    assert '<circle cx="12" cy="8" r="4">' in home
    assert 'labelKey: "nav.transactions"' in navigation
    assert 'labelKey: "nav.activity"' not in navigation
    assert 'icon: "↕"' not in navigation


def test_home_contains_replay_tutorial() -> None:
    client = TestClient(app)

    response = client.get("/home")
    styles = client.get("/static/css/pages/home.css")

    assert response.status_code == 200
    assert styles.status_code == 200

    assert 'href="/home?tour=start"' in response.text

    assert "Replay tutorial" in response.text
    assert ".tutorial-replay[hidden]" in styles.text
    assert "display: none !important;" in styles.text


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


def test_legacy_onboarding_route_is_removed() -> None:
    client = TestClient(app)

    response = client.get("/onboarding", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_unknown_page_redirects_by_authentication_and_store_context() -> None:
    anonymous = TestClient(app)
    response = anonymous.get("/missing-page", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    response = anonymous.get("/shop/missing/page", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/shop"

    assert anonymous.get("/api/missing-page").status_code == 404

    create_customer(anonymous)
    login(anonymous)
    response = anonymous.get("/missing-page", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/home"


def test_signup_supports_ios_name_autofill_and_valid_gender_values() -> None:
    client = TestClient(app)

    page = client.get("/signup").text
    script = client.get("/static/js/pages/signup.js").text

    assert 'autocomplete="section-signup given-name"' in page
    assert 'autocomplete="section-signup family-name"' in page
    assert 'autocapitalize="words"' in page
    assert '<option value="other">' in page
    assert '<option value="non_binary">' not in page
    assert "function normalizeAutofilledNames()" in script
    assert "normalizeAutofilledNames();" in script


def test_agent_route_serves_the_izzy_chat() -> None:
    client = TestClient(app)

    response = client.get("/agent")

    assert response.status_code == 200
    assert "agent.js" in response.text
    assert "Coming soon" not in response.text
    assert 'href="tel:+16615779964"' in response.text


def test_api_me_remains_protected() -> None:
    client = TestClient(app)

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_agent_pages_are_always_revalidated_by_the_browser() -> None:
    """Regression: /agent?intent=new_complaint kept showing a cached "coming soon" page."""

    client = TestClient(app)

    for url in ("/agent", "/agent?intent=new_complaint", "/home"):
        response = client.get(url)
        assert response.headers["cache-control"] == "no-cache"
        if url.startswith("/agent"):
            assert "agent.js" in response.text


def test_agent_hidden_panels_stay_hidden_despite_display_rules() -> None:
    """Regression: the "conversation has ended" panel showed on every open chat."""

    styles = TestClient(app).get("/static/css/pages/agent.css").text

    assert ".agent-page[hidden]," in styles
    assert ".agent-page [hidden] {" in styles
    assert "display: none !important;" in styles


def test_agent_phone_and_call_action_remain_in_the_sticky_mobile_header() -> None:
    client = TestClient(app)

    page = client.get("/agent").text
    styles = client.get("/static/css/pages/agent.css").text

    header_start = page.index('<header class="agent-header">')
    header_end = page.index("</header>", header_start)
    header = page[header_start:header_end]

    assert 'id="agent-phone-link"' in header
    assert 'id="agent-call"' in header
    assert "position: sticky;" in styles
    assert "grid-template-columns: auto minmax(max-content, 1fr) auto;" in styles
    assert "@media (max-width: 359px)" in styles
