"""Model factories shared by the repository tests (synthetic values only)."""

from datetime import UTC, date, datetime, timedelta

from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Accent, Customer, Gender
from webapp.backend.models.product import Product
from webapp.backend.models.session import AuthenticationMethod, CustomerSession
from webapp.backend.models.transaction import Transaction

NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)


def make_customer(customer_id: str = "C1", **overrides) -> Customer:
    values = {
        "customer_id": customer_id,
        "document_number": f"DOC-{customer_id}",
        "document_type": "FACTORED_ID",
        "first_name": "Ana",
        "last_name": "Silva",
        "date_of_birth": date(1990, 5, 17),
        "gender": Gender.FEMALE,
        "mobile_phone": None,
        "city": "Factored Village",
        "state": "Factored Fields",
        "country": "Factoredland",
        "detected_accent": Accent.PORTUGUESE,
        "segment": "Factored",
        "registration_date": NOW,
        "registration_branch_id": 1,
        "customer_status": "Active",
        "last_updated": NOW,
    }
    values.update(overrides)
    return Customer(**values)


def make_product(product_id: str = "P1", customer_id: str = "C1", **overrides) -> Product:
    values = {
        "product_id": product_id,
        "customer_id": customer_id,
        "product_type": "Credit Card",
        "product_number": "4111111111111111",
        "currency": "USD",
        "current_balance": 12.5,
        "credit_limit": 999_999_999.0,
        "opening_date": date(2026, 1, 1),
        "opening_branch_id": 1,
        "product_status": "Active",
        "opening_channel": "Web",
        "has_linked_app": True,
        "last_updated": NOW,
    }
    values.update(overrides)
    return Product(**values)


def make_transaction(
    transaction_id: str = "T1", customer_id: str = "C1", product_id: str = "P1", **overrides
) -> Transaction:
    values = {
        "transaction_id": transaction_id,
        "transaction_date": NOW,
        "process_date": NOW.date(),
        "product_id": product_id,
        "customer_id": customer_id,
        "transaction_type": "Purchase",
        "transaction_category": None,
        "amount": 129.9,
        "currency": "USD",
        "amount_usd": None,
        "channel": "Web",
        "merchant_name": None,
        "merchant_category": None,
        "transaction_country": "Unknown",
        "transaction_city": None,
        "transaction_status": "Approved",
        "is_fraud": False,
    }
    values.update(overrides)
    return Transaction(**values)


def make_complaint(complaint_id: str = "K1", customer_id: str = "C1", **overrides) -> Complaint:
    values = {
        "complaint_id": complaint_id,
        "creation_date": NOW,
        "process_date": NOW.date(),
        "customer_id": customer_id,
        "case_type": "Claim",
        "category": "Card Purchase",
        "subcategory": None,
        "reception_channel": "Web",
        "description": "Customer reported an unrecognized online purchase.",
        "claimed_amount": 129.9,
        "currency": "USD",
        "priority": "High",
        "status": "Open",
    }
    values.update(overrides)
    return Complaint(**values)


def make_session(session_id: str = "sess-1", customer_id: str = "C1", **overrides):
    values = {
        "session_id": session_id,
        "customer_id": customer_id,
        "authentication_method": AuthenticationMethod.FACTORED_ID,
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=12),
    }
    values.update(overrides)
    return CustomerSession(**values)
