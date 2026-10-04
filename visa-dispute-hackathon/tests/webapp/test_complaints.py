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


def test_complaints_page_is_available() -> None:
    client = TestClient(app)

    response = client.get("/complaints")

    assert response.status_code == 200
    assert "Complaints" in response.text
    assert "complaints.js" in response.text


def test_complaint_detail_page_is_available() -> None:
    client = TestClient(app)

    response = client.get("/complaints/CMP-DEMO-123")

    assert response.status_code == 200
    assert "Complaint details" in response.text
    assert "complaint-detail.js" in response.text


def test_complaints_require_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/complaints")

    assert response.status_code == 401


def test_complaint_detail_requires_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/complaints/CMP-DEMO-UNKNOWN")

    assert response.status_code == 401


def test_signup_starts_without_complaints() -> None:
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

    response = client.get("/api/complaints")

    assert response.status_code == 200
    assert response.json() == []


def test_customer_history_lists_every_owned_complaint() -> None:
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

    response = client.get("/api/complaints")

    assert response.status_code == 200

    complaints = response.json()

    assert len(complaints) == 2


def test_complaints_are_sorted_newest_first() -> None:
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

    response = client.get("/api/complaints")

    assert response.status_code == 200

    complaints = response.json()

    dates = [complaint["creation_date"] for complaint in complaints]

    assert dates == sorted(
        dates,
        reverse=True,
    )


def test_complaint_list_contains_expected_fields() -> None:
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

    response = client.get("/api/complaints")

    assert response.status_code == 200

    complaint = response.json()[0]

    assert "complaint_id" in complaint
    assert "creation_date" in complaint
    assert "case_type" in complaint
    assert "category" in complaint
    assert "subcategory" in complaint
    assert "claimed_amount" in complaint
    assert "currency" in complaint
    assert "status" in complaint
    assert "priority" in complaint


def test_demo_history_contains_open_and_resolved_complaints() -> None:
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

    response = client.get("/api/complaints")

    assert response.status_code == 200

    complaints = response.json()

    statuses = {complaint["status"] for complaint in complaints}

    assert "In Review" in statuses
    assert "Resolved" in statuses


def test_demo_complaints_have_claimed_amounts() -> None:
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

    complaints = client.get("/api/complaints").json()

    amounts = {complaint["claimed_amount"] for complaint in complaints}

    assert 129.90 in amounts
    assert 8.75 in amounts


def test_customer_sees_only_own_complaints() -> None:
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

    response = first_client.get("/api/complaints")

    assert response.status_code == 200

    returned = response.json()

    assert len(returned) == 2

    first_customer = customer_repository.get_by_document("111111")

    assert first_customer is not None

    owned = complaint_repository.list_by_customer(first_customer.customer_id)

    returned_ids = {complaint["complaint_id"] for complaint in returned}

    owned_ids = {complaint.complaint_id for complaint in owned}

    assert returned_ids == owned_ids


def test_customer_can_view_own_complaint_detail() -> None:
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

    complaints = client.get("/api/complaints").json()

    complaint_id = complaints[0]["complaint_id"]

    response = client.get(f"/api/complaints/{complaint_id}")

    assert response.status_code == 200

    complaint = response.json()

    assert complaint["complaint_id"] == complaint_id

    assert "description" in complaint
    assert "reception_channel" in complaint
    assert "resolution" in complaint
    assert "compensation_granted" in complaint
    assert "resolution_days" in complaint


def test_resolved_complaint_contains_resolution_information() -> None:
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

    complaints = client.get("/api/complaints").json()

    resolved = next(complaint for complaint in complaints if complaint["status"] == "Resolved")

    response = client.get(f"/api/complaints/{resolved['complaint_id']}")

    assert response.status_code == 200

    detail = response.json()

    assert detail["resolution"] is not None
    assert detail["resolution_date"] is not None
    assert detail["resolution_days"] == 2
    assert detail["compensation_granted"] == 8.75


def test_open_complaint_has_no_final_resolution() -> None:
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

    complaints = client.get("/api/complaints").json()

    open_complaint = next(
        complaint for complaint in complaints if complaint["status"] == "In Review"
    )

    response = client.get(f"/api/complaints/{open_complaint['complaint_id']}")

    assert response.status_code == 200

    detail = response.json()

    assert detail["resolution"] is None
    assert detail["resolution_date"] is None
    assert detail["closing_date"] is None
    assert detail["compensation_granted"] is None


def test_unknown_complaint_returns_404() -> None:
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

    response = client.get("/api/complaints/CMP-DOES-NOT-EXIST")

    assert response.status_code == 404


def test_customer_cannot_view_other_customer_complaint() -> None:
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

    second_complaints = second_client.get("/api/complaints")

    assert second_complaints.status_code == 200

    other_complaint_id = second_complaints.json()[0]["complaint_id"]

    login(
        first_client,
        "111111",
    )

    response = first_client.get(f"/api/complaints/{other_complaint_id}")

    assert response.status_code == 404
