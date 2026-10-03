from fakes import (
    add_history,
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
    factored_id: str,
    first_name: str,
    phone: str,
    history: bool = True,
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

    created = response.json()
    if history:
        add_history(created["customer_id"])

    return created


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


def test_transactions_page_is_available() -> None:
    client = TestClient(app)

    response = client.get("/transactions")

    assert response.status_code == 200
    assert "Transactions" in response.text
    assert "transactions.js" in response.text


def test_transaction_detail_page_is_available() -> None:
    client = TestClient(app)

    response = client.get("/transactions/TRX-DEMO-123")

    assert response.status_code == 200
    assert "Transaction details" in response.text
    assert "transaction-detail.js" in response.text


def test_transactions_require_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/transactions")

    assert response.status_code == 401


def test_transaction_detail_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/transactions/TRX-DEMO-UNKNOWN")

    assert response.status_code == 401


def test_signup_starts_without_transactions() -> None:
    """Regression: signup used to invent hardcoded history; activity now comes from the shop."""

    client = TestClient(app)

    create_customer(
        client,
        factored_id="111111",
        first_name="Gabriel",
        phone="+5511981020050",
        history=False,
    )

    login(
        client,
        "111111",
    )

    response = client.get("/api/transactions")

    assert response.status_code == 200
    assert response.json() == []


def test_customer_history_lists_every_owned_transaction() -> None:
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

    response = client.get("/api/transactions")

    assert response.status_code == 200

    transactions = response.json()

    assert len(transactions) == 4


def test_transactions_are_sorted_newest_first() -> None:
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

    response = client.get("/api/transactions")

    assert response.status_code == 200

    transactions = response.json()

    dates = [transaction["transaction_date"] for transaction in transactions]

    assert dates == sorted(
        dates,
        reverse=True,
    )


def test_transaction_list_contains_expected_fields() -> None:
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

    response = client.get("/api/transactions")

    assert response.status_code == 200

    transaction = response.json()[0]

    assert "transaction_id" in transaction
    assert "transaction_date" in transaction
    assert "product_id" in transaction
    assert "card_last_four" in transaction
    assert "merchant_name" in transaction
    assert "amount" in transaction
    assert "currency" in transaction
    assert "transaction_status" in transaction
    assert "is_fraud" in transaction


def test_transaction_list_does_not_expose_full_card_number() -> None:
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

    response = client.get("/api/transactions")

    assert response.status_code == 200

    transaction = response.json()[0]

    assert "product_number" not in transaction
    assert len(transaction["card_last_four"]) == 4


def test_demo_history_contains_fraud_indicator() -> None:
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

    response = client.get("/api/transactions")

    assert response.status_code == 200

    transactions = response.json()

    suspicious = [transaction for transaction in transactions if transaction["is_fraud"]]

    assert len(suspicious) == 1

    assert suspicious[0]["merchant_name"] == "Shady Business"


def test_customer_sees_only_own_transactions() -> None:
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
        "111111",
    )

    response = first_client.get("/api/transactions")

    assert response.status_code == 200

    transactions = response.json()

    assert len(transactions) == 4

    first_customer = customer_repository.get_by_document("111111")

    assert first_customer is not None

    owned_transactions = transaction_repository.list_by_customer(first_customer.customer_id)

    assert len(owned_transactions) == 4

    returned_ids = {transaction["transaction_id"] for transaction in transactions}

    owned_ids = {transaction.transaction_id for transaction in owned_transactions}

    assert returned_ids == owned_ids


def test_customer_can_view_own_transaction_detail() -> None:
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

    list_response = client.get("/api/transactions")

    assert list_response.status_code == 200

    transaction_id = list_response.json()[0]["transaction_id"]

    response = client.get(f"/api/transactions/{transaction_id}")

    assert response.status_code == 200

    transaction = response.json()

    assert transaction["transaction_id"] == transaction_id

    assert "merchant_category" in transaction
    assert "transaction_country" in transaction
    assert "transaction_city" in transaction
    assert "fraud_score" in transaction


def test_unknown_transaction_returns_404() -> None:
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

    response = client.get("/api/transactions/TRX-DOES-NOT-EXIST")

    assert response.status_code == 404


def test_customer_cannot_view_other_customer_transaction() -> None:
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
        second_client,
        "222222",
    )

    second_transactions = second_client.get("/api/transactions")

    assert second_transactions.status_code == 200

    other_transaction_id = second_transactions.json()[0]["transaction_id"]

    login(
        first_client,
        "111111",
    )

    response = first_client.get(f"/api/transactions/{other_transaction_id}")

    assert response.status_code == 404


def test_suspicious_transaction_detail_preserves_fraud_flag() -> None:
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

    transactions = client.get("/api/transactions").json()

    suspicious = next(transaction for transaction in transactions if transaction["is_fraud"])

    response = client.get(f"/api/transactions/{suspicious['transaction_id']}")

    assert response.status_code == 200

    detail = response.json()

    assert detail["is_fraud"] is True
    assert detail["fraud_score"] == 0.94
    assert detail["merchant_name"] == "Shady Business"
