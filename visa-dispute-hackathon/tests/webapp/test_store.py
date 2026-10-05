from datetime import timedelta

import pytest
from fakes import (
    complaint_repository,
    customer_repository,
    product_repository,
    session_repository,
    transaction_repository,
)
from fastapi.testclient import TestClient

from webapp.backend.api.routes.store import get_store_service, store_catalog
from webapp.backend.main import app
from webapp.backend.services.store import (
    FOREIGN_FRAUD_MERCHANTS,
    SOUTH_ASIAN_LOCATIONS,
    RandomAnomalyStrategy,
    StoreService,
)


class DuplicateStrategy:
    def build(self, purchase):
        return purchase.model_copy(
            update={
                "transaction_id": "TRX-SHADY-DUPLICATE",
                "transaction_date": purchase.transaction_date + timedelta(seconds=1),
                "transaction_category": "Duplicate card charge",
            }
        )


class ForeignFraudStrategy:
    def __init__(self, country: str, city: str) -> None:
        self.country = country
        self.city = city

    def build(self, purchase):
        return purchase.model_copy(
            update={
                "transaction_id": f"TRX-FRAUD-{self.country}",
                "transaction_date": purchase.transaction_date + timedelta(seconds=1),
                "merchant_name": "Royal Bengal Electronics Export",
                "transaction_category": "Unrecognized luxury electronics",
                "amount": 1900.0,
                "amount_usd": 1900.0,
                "transaction_country": self.country,
                "transaction_city": self.city,
                "is_fraud": True,
                "fraud_score": 0.97,
            }
        )


class FraudMerchantSequenceGenerator:
    def __init__(self) -> None:
        self.merchant_index = 0

    def choice(self, options):
        if options == ("duplicate", "foreign_fraud"):
            return "foreign_fraud"
        if options == SOUTH_ASIAN_LOCATIONS:
            return SOUTH_ASIAN_LOCATIONS[self.merchant_index % len(SOUTH_ASIAN_LOCATIONS)]
        merchant = FOREIGN_FRAUD_MERCHANTS[self.merchant_index]
        self.merchant_index += 1
        return merchant

    @staticmethod
    def randrange(_start, _stop):
        return 190000


def clear_repositories() -> None:
    customer_repository._customers.clear()
    product_repository._products.clear()
    transaction_repository._transactions.clear()
    complaint_repository._complaints.clear()
    session_repository._sessions.clear()


def create_customer(
    client: TestClient, factored_id: str = "123456", phone: str = "+5511999990001"
) -> dict:
    response = client.post(
        "/api/customers",
        json={
            "first_name": "Shady",
            "last_name": "Shopper",
            "date_of_birth": "1990-01-01",
            "gender": "prefer_not_to_say",
            "mobile_phone": phone,
            "preferred_accent": "english",
            "factored_id": factored_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def login(client: TestClient, factored_id: str = "123456") -> None:
    assert client.post("/api/auth/login", json={"factored_id": factored_id}).status_code == 200


def checkout_payload(card_id: str, product_id: str = "wifi-rock") -> dict:
    return {
        "card_product_id": card_id,
        "items": [{"product_id": product_id, "quantity": 2}],
    }


def use_anomaly_strategy(strategy) -> None:
    app.dependency_overrides[get_store_service] = lambda: StoreService(
        store_catalog, product_repository, transaction_repository, strategy
    )


def setup_function() -> None:
    clear_repositories()
    use_anomaly_strategy(DuplicateStrategy())


def test_store_receipt_sends_transactions_back_to_bank_home() -> None:
    page = TestClient(app).get("/shop/cart").text

    assert 'href="/transactions?return=home"' in page


def teardown_function() -> None:
    clear_repositories()
    app.dependency_overrides.pop(get_store_service, None)


def test_store_pages_are_available() -> None:
    client = TestClient(app)

    assert "SHADY" in client.get("/shop").text
    assert "store.js" in client.get("/shop").text
    assert "store-product.js" in client.get("/shop/products/wifi-rock").text
    assert "store-cart.js" in client.get("/shop/cart").text


def test_missing_store_product_returns_customer_to_catalog() -> None:
    client = TestClient(app)
    script = client.get("/static/js/pages/store-product.js").text

    assert 'window.location.replace("/shop")' in script


def test_catalog_and_product_detail_use_typed_mock_products() -> None:
    client = TestClient(app)

    catalog = client.get("/api/store/products")
    detail = client.get("/api/store/products/wifi-rock")

    assert catalog.status_code == 200
    assert len(catalog.json()) >= 6
    assert detail.status_code == 200
    assert detail.json()["name"] == "Wi-Fi Extender Rock"
    assert detail.json()["price"] == 64.5
    assert client.get("/api/store/products/not-real").status_code == 404


def test_checkout_requires_authentication() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/store/checkout",
        json=checkout_payload("unknown-card"),
    )

    assert response.status_code == 401


def test_duplicate_checkout_creates_purchase_and_duplicate_visible_in_activity() -> None:
    client = TestClient(app)
    customer = create_customer(client)
    login(client)
    card_id = customer["demo_card"]["product_id"]
    before = client.get("/api/transactions").json()

    response = client.post("/api/store/checkout", json=checkout_payload(card_id))

    assert response.status_code == 200
    assert response.json()["total"] == 129.0
    after = client.get("/api/transactions").json()
    assert len(after) == len(before) + 2
    created = after[:2]
    assert len({transaction["transaction_id"] for transaction in created}) == 2
    assert {transaction["amount"] for transaction in created} == {129.0}
    assert {transaction["merchant_name"] for transaction in created} == {"Shady Business"}


@pytest.mark.parametrize(("country", "city"), SOUTH_ASIAN_LOCATIONS)
def test_foreign_fraud_scenario_supports_every_configured_location(country: str, city: str) -> None:
    client = TestClient(app)
    customer = create_customer(client)
    login(client)
    use_anomaly_strategy(ForeignFraudStrategy(country, city))

    response = client.post(
        "/api/store/checkout",
        json=checkout_payload(customer["demo_card"]["product_id"], "left-handed-mug"),
    )

    assert response.status_code == 200
    created = client.get("/api/transactions").json()[:2]
    fraud = next(transaction for transaction in created if transaction["is_fraud"])
    detail = client.get(f"/api/transactions/{fraud['transaction_id']}").json()
    assert detail["transaction_country"] == country
    assert detail["transaction_city"] == city
    assert detail["amount"] == 1900.0


def test_random_fraud_scenario_can_create_ten_searchable_merchants() -> None:
    client = TestClient(app)
    customer = create_customer(client)
    login(client)
    card_id = customer["demo_card"]["product_id"]
    use_anomaly_strategy(RandomAnomalyStrategy(FraudMerchantSequenceGenerator()))

    for _merchant in FOREIGN_FRAUD_MERCHANTS:
        response = client.post("/api/store/checkout", json=checkout_payload(card_id))
        assert response.status_code == 200

    transactions = client.get("/api/transactions").json()
    generated_merchants = {
        transaction["merchant_name"]
        for transaction in transactions
        if transaction["transaction_category"] == "Unrecognized luxury electronics"
    }

    assert len(FOREIGN_FRAUD_MERCHANTS) == 10
    assert generated_merchants == {
        merchant_name for merchant_name, _category in FOREIGN_FRAUD_MERCHANTS
    }


def test_blocked_card_rejects_checkout_without_writes() -> None:
    client = TestClient(app)
    customer = create_customer(client)
    login(client)
    card_id = customer["demo_card"]["product_id"]
    client.post(f"/api/products/{card_id}/block")
    before = len(client.get("/api/transactions").json())

    response = client.post("/api/store/checkout", json=checkout_payload(card_id))

    assert response.status_code == 422
    assert "blocked or inactive" in response.json()["detail"]
    assert len(client.get("/api/transactions").json()) == before


def test_customer_cannot_use_another_customers_card() -> None:
    first = TestClient(app)
    second = TestClient(app)
    create_customer(first, "111111", "+5511999990001")
    other = create_customer(second, "222222", "+5511999990002")
    login(first, "111111")

    response = first.post(
        "/api/store/checkout",
        json=checkout_payload(other["demo_card"]["product_id"]),
    )

    assert response.status_code == 422
    assert "own demo credit cards" in response.json()["detail"]


def test_checkout_recalculates_prices_and_rejects_tampering() -> None:
    client = TestClient(app)
    customer = create_customer(client)
    login(client)
    payload = checkout_payload(customer["demo_card"]["product_id"])
    payload["items"][0]["price"] = 0.01

    response = client.post("/api/store/checkout", json=payload)

    assert response.status_code == 422
    assert (
        client.post(
            "/api/store/checkout",
            json=checkout_payload(customer["demo_card"]["product_id"], "missing-product"),
        ).status_code
        == 422
    )


def test_invalid_quantities_and_empty_cart_are_rejected() -> None:
    client = TestClient(app)
    customer = create_customer(client)
    login(client)
    card_id = customer["demo_card"]["product_id"]

    assert (
        client.post(
            "/api/store/checkout",
            json={"card_product_id": card_id, "items": []},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/store/checkout",
            json={
                "card_product_id": card_id,
                "items": [{"product_id": "wifi-rock", "quantity": 0}],
            },
        ).status_code
        == 422
    )
