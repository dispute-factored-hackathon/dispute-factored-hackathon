from fastapi.testclient import TestClient

from webapp.backend.main import app
from webapp.backend.repositories.mock import (
    customer_repository,
    product_repository,
    session_repository,
)


def clear_repositories() -> None:
    customer_repository._customers.clear()
    product_repository._products.clear()
    session_repository._sessions.clear()


def create_customer(
    client: TestClient,
    *,
    factored_id: str,
    first_name: str,
    phone: str,
) -> dict:
    response = client.post(
        "/api/customers",
        json={
            "first_name": first_name,
            "last_name": "Factored",
            "date_of_birth": "2000-01-01",
            "gender": "male",
            "mobile_phone": phone,
            "preferred_accent": "english",
            "factored_id": factored_id,
        },
    )

    assert response.status_code == 201

    return response.json()


def login(
    client: TestClient,
    factored_id: str,
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


def test_cards_page_is_available() -> None:
    client = TestClient(app)

    response = client.get("/cards")

    assert response.status_code == 200
    assert "Cards" in response.text
    assert "cards.js" in response.text


def test_products_require_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/products")

    assert response.status_code == 401


def test_customer_sees_own_card() -> None:
    client = TestClient(app)

    created = create_customer(
        client,
        factored_id="111111",
        first_name="Gabriel",
        phone="+5511981020050",
    )

    login(
        client,
        "111111",
    )

    response = client.get("/api/products")

    assert response.status_code == 200

    products = response.json()

    assert len(products) == 1

    product = products[0]

    assert product["product_id"] == created["demo_card"]["product_id"]

    assert product["product_status"] == "Active"


def test_card_number_is_masked() -> None:
    client = TestClient(app)

    create_customer(
        client,
        factored_id="111111",
        first_name="Gabriel",
        phone="+5511981020050",
    )

    login(
        client,
        "111111",
    )

    response = client.get("/api/products")

    assert response.status_code == 200

    product = response.json()[0]

    assert "product_number" not in product

    assert product["masked_number"].startswith("•••• •••• •••• ")

    assert len(product["last_four"]) == 4

    assert product["masked_number"].endswith(product["last_four"])


def test_customer_does_not_see_other_customer_card() -> None:
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

    login(
        first_client,
        "111111",
    )

    response = first_client.get("/api/products")

    assert response.status_code == 200

    products = response.json()

    product_ids = {product["product_id"] for product in products}

    assert first["demo_card"]["product_id"] in product_ids

    assert second["demo_card"]["product_id"] not in product_ids


def test_customer_can_block_card() -> None:
    client = TestClient(app)

    created = create_customer(
        client,
        factored_id="111111",
        first_name="Gabriel",
        phone="+5511981020050",
    )

    login(
        client,
        "111111",
    )

    product_id = created["demo_card"]["product_id"]

    response = client.post(f"/api/products/{product_id}/block")

    assert response.status_code == 200

    assert response.json()["product_status"] == "Blocked"

    products = client.get("/api/products").json()

    assert products[0]["product_status"] == "Blocked"


def test_block_is_idempotent() -> None:
    client = TestClient(app)

    created = create_customer(
        client,
        factored_id="111111",
        first_name="Gabriel",
        phone="+5511981020050",
    )

    login(
        client,
        "111111",
    )

    product_id = created["demo_card"]["product_id"]

    first = client.post(f"/api/products/{product_id}/block")

    second = client.post(f"/api/products/{product_id}/block")

    assert first.status_code == 200
    assert second.status_code == 200

    assert second.json()["product_status"] == "Blocked"


def test_customer_can_unblock_card() -> None:
    client = TestClient(app)

    created = create_customer(
        client,
        factored_id="111111",
        first_name="Gabriel",
        phone="+5511981020050",
    )

    login(
        client,
        "111111",
    )

    product_id = created["demo_card"]["product_id"]

    block_response = client.post(f"/api/products/{product_id}/block")

    assert block_response.status_code == 200

    response = client.post(f"/api/products/{product_id}/unblock")

    assert response.status_code == 200

    assert response.json()["product_status"] == "Active"


def test_unblock_is_idempotent() -> None:
    client = TestClient(app)

    created = create_customer(
        client,
        factored_id="111111",
        first_name="Gabriel",
        phone="+5511981020050",
    )

    login(
        client,
        "111111",
    )

    product_id = created["demo_card"]["product_id"]

    response = client.post(f"/api/products/{product_id}/unblock")

    assert response.status_code == 200

    assert response.json()["product_status"] == "Active"


def test_customer_cannot_block_another_customers_card() -> None:
    first_client = TestClient(app)
    second_client = TestClient(app)

    create_customer(
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

    login(
        first_client,
        "111111",
    )

    other_product_id = second["demo_card"]["product_id"]

    response = first_client.post(f"/api/products/{other_product_id}/block")

    assert response.status_code == 404

    second_product = product_repository.get_by_id(other_product_id)

    assert second_product is not None

    assert second_product.product_status == "Active"


def test_customer_cannot_unblock_another_customers_card() -> None:
    first_client = TestClient(app)
    second_client = TestClient(app)

    create_customer(
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

    other_product_id = second["demo_card"]["product_id"]

    login(
        second_client,
        "222222",
    )

    block_response = second_client.post(f"/api/products/{other_product_id}/block")

    assert block_response.status_code == 200

    login(
        first_client,
        "111111",
    )

    response = first_client.post(f"/api/products/{other_product_id}/unblock")

    assert response.status_code == 404

    second_product = product_repository.get_by_id(other_product_id)

    assert second_product is not None

    assert second_product.product_status == "Blocked"
