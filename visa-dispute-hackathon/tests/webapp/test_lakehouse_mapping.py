"""Pure mapping from lakehouse `silver` rows to app models (synthetic rows only)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from webapp.backend.db import lakehouse_mapping as mapping
from webapp.backend.models.customer import Accent, Gender

LOADED_AT = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def customer_row(**overrides) -> dict:
    row = {
        "customer_id": "CLI-0001",
        "document_number": 12345678,
        "document_type": "CC",
        "first_name": "GUILLERMO  DIEGO",
        "last_name": "PÉREZ",
        "date_of_birth": date(1985, 3, 4),
        "gender": "M",
        "mobile_phone": "+573001112233",
        "city": "BOGOTÁ",
        "state": "CUNDINAMARCA",
        "country": "COLOMBIA",
        "detected_accent": None,
        "segment": "PREMIUM",
        "registration_date": datetime(2020, 1, 1, 9, 30),
        "registration_branch_id": "BR-017",
        "customer_status": "ACTIVE",
    }
    row.update(overrides)
    return row


def test_customer_labels_are_title_cased_so_login_accepts_active_customers():
    customer = mapping.map_customer(customer_row(), loaded_at=LOADED_AT)

    assert customer.customer_status == "Active"
    assert customer.first_name == "Guillermo Diego"
    assert customer.last_name == "Pérez"
    assert customer.document_number == "12345678"
    assert customer.segment == "Premium"
    assert customer.gender is Gender.MALE
    assert customer.registration_date == datetime(2020, 1, 1, 9, 30, tzinfo=UTC)
    assert customer.onboarding_completed is True  # dataset customers are not judges


@pytest.mark.parametrize("status", ["INACTIVE", "SUSPENDED", "CLOSED"])
def test_non_active_statuses_never_become_active(status: str):
    customer = mapping.map_customer(customer_row(customer_status=status), loaded_at=LOADED_AT)

    assert customer.customer_status == status.capitalize()
    assert customer.customer_status != "Active"


def test_accent_comes_from_the_dataset_then_the_country_then_english():
    explicit = mapping.map_customer(customer_row(detected_accent="MEXICAN"), loaded_at=LOADED_AT)
    by_country = mapping.map_customer(customer_row(), loaded_at=LOADED_AT)
    fallback = mapping.map_customer(customer_row(country="CANADA"), loaded_at=LOADED_AT)

    assert explicit.detected_accent is Accent.MEXICAN_SPANISH
    assert by_country.detected_accent is Accent.COLOMBIAN_SPANISH
    assert fallback.detected_accent is Accent.ENGLISH


def test_branch_ids_are_stable_integers():
    first = mapping.branch_number("BR-017")

    assert first == mapping.branch_number("BR-017")
    assert first != mapping.branch_number("BR-018")
    assert 0 <= first < 1_000_000
    assert mapping.branch_number(None) == 0


def test_labels_keep_acronyms_and_drop_blank_values():
    assert mapping.label("POS") == "POS"
    assert mapping.label("ATM  WITHDRAWAL") == "ATM Withdrawal"
    assert mapping.label("IN PROCESS") == "In Process"
    assert mapping.label("   ") is None
    assert mapping.label(None) is None


def test_card_numbers_keep_only_the_last_four_digits():
    product = mapping.map_product(
        {
            "product_id": "PRD-1",
            "customer_id": "CLI-0001",
            "product_type": "CREDIT CARD",
            "product_number": "4111222233334444",
            "currency": "COP",
            "current_balance": Decimal("10.50"),
            "credit_limit": None,
            "opening_date": date(2021, 5, 1),
            "opening_branch_id": "BR-017",
            "product_status": "ACTIVE",
            "opening_channel": "BRANCH",
            "has_linked_app": 1,
        },
        loaded_at=LOADED_AT,
    )

    assert product.product_number == "************4444"
    assert "4111" not in product.product_number
    assert product.product_type == "Credit Card"
    assert product.credit_limit == 0.0  # debit cards have no limit in the lakehouse
    assert product.current_balance == 10.5


def transaction_row(**overrides) -> dict:
    row = {
        "transaction_id": "TRX-1",
        "transaction_date": datetime(2026, 9, 1, 18, 5),
        "process_date": date(2026, 9, 2),
        "product_id": "PRD-1",
        "customer_id": "CLI-0001",
        "transaction_type": "PURCHASE",
        "transaction_category": "ONLINE SHOPPING",
        "amount": Decimal("129.90"),
        "currency": "COP",
        "amount_usd": Decimal("0.03"),
        "channel": "POS",
        "branch_id": None,
        "merchant_name": "SHADY BUSINESS",
        "merchant_category": "RETAIL",
        "transaction_country": "COLOMBIA",
        "transaction_city": None,
        "transaction_status": "APPROVED",
        "response_code": "00",
        "is_fraud": True,
        "fraud_score": Decimal("0.94"),
        "transaction_location": "POINT (4.711 -74.0721)",
    }
    row.update(overrides)
    return row


def test_transaction_mapping_parses_location_and_keeps_fraud_labels_by_default():
    transaction = mapping.map_transaction(transaction_row())

    assert (transaction.latitude, transaction.longitude) == (4.711, -74.0721)
    assert transaction.channel == "POS"
    assert transaction.transaction_status == "Approved"
    assert transaction.merchant_name == "Shady Business"
    assert transaction.transaction_city is None
    assert transaction.is_fraud is True
    assert transaction.fraud_score == 0.94
    assert transaction.transaction_date.tzinfo is UTC


def test_fraud_labels_can_be_hidden():
    transaction = mapping.map_transaction(transaction_row(), keep_fraud_labels=False)

    assert transaction.is_fraud is False
    assert transaction.fraud_score is None


@pytest.mark.parametrize("location", [None, "", "LINESTRING (1 2, 3 4)", "POINT (north south)"])
def test_unparseable_locations_become_empty_coordinates(location):
    transaction = mapping.map_transaction(transaction_row(transaction_location=location))

    assert (transaction.latitude, transaction.longitude) == (None, None)


def test_missing_process_date_falls_back_to_the_transaction_date():
    transaction = mapping.map_transaction(transaction_row(process_date=None))

    assert transaction.process_date == date(2026, 9, 1)


def test_complaint_mapping_title_cases_statuses_the_frontend_translates():
    complaint = mapping.map_complaint(
        {
            "complaint_id": "CMP-1",
            "creation_date": datetime(2026, 8, 1, 10, 0),
            "process_date": None,
            "customer_id": "CLI-0001",
            "case_type": "CLAIM",
            "category": "CARD PURCHASE",
            "subcategory": None,
            "reception_channel": "CALL CENTER",
            "description": "Synthetic complaint text.",
            "claimed_amount": None,
            "currency": None,
            "priority": "HIGH",
            "status": "RESOLVED",
            "sla_breached": 0,
            "is_repeat_complainer": 1,
        }
    )

    assert complaint.status == "Resolved"
    assert complaint.reception_channel == "Call Center"
    assert complaint.claimed_amount == 0.0
    assert complaint.currency == "USD"
    assert complaint.process_date == date(2026, 8, 1)
    assert complaint.is_repeat_complainer is True


def test_requested_columns_never_include_contact_or_financial_profile_fields():
    requested = {
        *mapping.CUSTOMER_COLUMNS,
        *mapping.PRODUCT_COLUMNS,
        *mapping.TRANSACTION_COLUMNS,
        *mapping.COMPLAINT_COLUMNS,
    }

    for forbidden in ("email", "address", "monthly_income", "credit_score"):
        assert forbidden not in requested
