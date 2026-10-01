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
    phone: str = "+5511981020050",
) -> dict:
    response = client.post(
        "/api/customers",
        json={
            "first_name": "Gabriel",
            "last_name": "Silveira",
            "date_of_birth": "2000-01-01",
            "gender": "male",
            "mobile_phone": phone,
            "preferred_accent": "portuguese",
            "factored_id": factored_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def login(client: TestClient, factored_id: str = "123456") -> None:
    response = client.post("/api/auth/login", json={"factored_id": factored_id})
    assert response.status_code == 200


def update_payload(**changes: object) -> dict:
    payload = {
        "first_name": "Gabriel",
        "last_name": "Silveira",
        "date_of_birth": "2000-01-01",
        "gender": "male",
        "mobile_phone": "+5511981020050",
        "preferred_accent": "portuguese",
    }
    payload.update(changes)
    return payload


def setup_function() -> None:
    clear_repositories()


def teardown_function() -> None:
    clear_repositories()


def test_profile_page_is_real_and_editable() -> None:
    response = TestClient(app).get("/profile")

    assert response.status_code == 200
    assert "Your profile" in response.text
    assert "profile.js" in response.text
    assert "Save changes" in response.text
    assert "Coming soon" not in response.text


def test_profile_requires_authentication() -> None:
    client = TestClient(app)

    assert client.get("/api/customers/profile").status_code == 401
    assert client.patch("/api/customers/profile", json=update_payload()).status_code == 401


def test_profile_returns_authenticated_customer_data() -> None:
    client = TestClient(app)
    created = create_customer(client)
    login(client)

    response = client.get("/api/customers/profile")

    assert response.status_code == 200
    assert response.json() == {
        "customer_id": created["customer_id"],
        "factored_id": "123456",
        "first_name": "Gabriel",
        "last_name": "Silveira",
        "date_of_birth": "2000-01-01",
        "gender": "male",
        "mobile_phone": "+5511981020050",
        "preferred_accent": "portuguese",
        "customer_status": "Active",
    }


def test_customer_can_update_editable_profile_fields() -> None:
    client = TestClient(app)
    created = create_customer(client)
    login(client)

    response = client.patch(
        "/api/customers/profile",
        json=update_payload(
            first_name="  gabriela  ",
            last_name="de souza",
            date_of_birth="1998-04-12",
            gender="female",
            mobile_phone="+573001112233",
            preferred_accent="colombian_spanish",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Gabriela"
    assert body["last_name"] == "De Souza"
    assert body["mobile_phone"] == "+573001112233"
    assert body["preferred_accent"] == "colombian_spanish"

    stored = customer_repository.get_by_id(created["customer_id"])
    assert stored is not None
    assert stored.first_name == "Gabriela"
    assert stored.detected_accent == "colombian_spanish"


def test_factored_id_cannot_be_submitted_or_changed() -> None:
    client = TestClient(app)
    created = create_customer(client)
    login(client)

    response = client.patch(
        "/api/customers/profile",
        json=update_payload(factored_id="999999"),
    )

    assert response.status_code == 422
    stored = customer_repository.get_by_id(created["customer_id"])
    assert stored is not None
    assert stored.document_number == "123456"


def test_phone_must_remain_unique_between_customers() -> None:
    client = TestClient(app)
    create_customer(client, factored_id="111111", phone="+5511111111111")
    create_customer(client, factored_id="222222", phone="+5522222222222")
    login(client, "111111")

    response = client.patch(
        "/api/customers/profile",
        json=update_payload(mobile_phone="+5522222222222"),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Phone number already exists."


def test_profile_validation_rejects_invalid_values() -> None:
    client = TestClient(app)
    create_customer(client)
    login(client)

    invalid_phone = client.patch(
        "/api/customers/profile",
        json=update_payload(mobile_phone="11981020050"),
    )
    future_birth_date = client.patch(
        "/api/customers/profile",
        json=update_payload(date_of_birth="2999-01-01"),
    )

    assert invalid_phone.status_code == 422
    assert future_birth_date.status_code == 422


def test_profile_updates_are_isolated_by_session() -> None:
    first_client = TestClient(app)
    second_client = TestClient(app)
    create_customer(first_client, factored_id="111111", phone="+5511111111111")
    create_customer(second_client, factored_id="222222", phone="+5522222222222")
    login(first_client, "111111")
    login(second_client, "222222")

    response = first_client.patch(
        "/api/customers/profile",
        json=update_payload(first_name="Updated", mobile_phone="+5533333333333"),
    )

    assert response.status_code == 200
    assert first_client.get("/api/customers/profile").json()["first_name"] == "Updated"
    assert second_client.get("/api/customers/profile").json()["first_name"] == "Gabriel"
