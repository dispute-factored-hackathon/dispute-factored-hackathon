"""Pure mapping from lakehouse `silver` rows to the web app's models (no network, no database).

The lakehouse stores upper-case labels, text branch ids and DuckDB-specific types. The app
compares exact labels (``customer_status == "Active"``) and its frontend translates exact English
strings (``Resolved``, ``Credit Card``, ``POS``), so values are normalised here, once.

Data minimisation: only the columns listed in the ``*_COLUMNS`` tuples are ever requested.
Contact details, income, credit score, address and marketing fields are never copied.
"""

import re
import zlib
from datetime import UTC, date, datetime
from typing import Any

from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Accent, Customer, Gender
from webapp.backend.models.product import Product
from webapp.backend.models.transaction import Transaction

CARD_TYPES = ("CREDIT CARD", "DEBIT CARD")

CUSTOMER_COLUMNS = (
    "customer_id",
    "document_number",
    "document_type",
    "first_name",
    "last_name",
    "date_of_birth",
    "gender",
    "mobile_phone",
    "city",
    "state",
    "country",
    "detected_accent",
    "segment",
    "registration_date",
    "registration_branch_id",
    "customer_status",
)
# The card number is masked inside the SQL query itself (see seed_lakehouse), so the full
# number never reaches this process; `product_number` below already ends in the real last four.
PRODUCT_COLUMNS = (
    "product_id",
    "customer_id",
    "product_type",
    "product_number",
    "currency",
    "current_balance",
    "credit_limit",
    "opening_date",
    "opening_branch_id",
    "product_status",
    "opening_channel",
    "has_linked_app",
)
TRANSACTION_COLUMNS = (
    "transaction_id",
    "transaction_date",
    "process_date",
    "product_id",
    "customer_id",
    "transaction_type",
    "transaction_category",
    "amount",
    "currency",
    "amount_usd",
    "channel",
    "branch_id",
    "merchant_name",
    "merchant_category",
    "transaction_country",
    "transaction_city",
    "transaction_status",
    "response_code",
    "is_fraud",
    "fraud_score",
    "transaction_location",
)
COMPLAINT_COLUMNS = (
    "complaint_id",
    "creation_date",
    "process_date",
    "customer_id",
    "case_type",
    "category",
    "subcategory",
    "reception_channel",
    "affected_product_id",
    "related_branch_id",
    "origin_interaction_id",
    "description",
    "claimed_amount",
    "currency",
    "priority",
    "status",
    "assigned_agent_id",
    "assignment_date",
    "first_response_date",
    "resolution_date",
    "closing_date",
    "sla_breached",
    "resolution_days",
    "resolution",
    "compensation_granted",
    "resolution_satisfaction",
    "is_repeat_complainer",
)

_ACRONYMS = {"POS", "ATM", "SLA", "ID"}
_GENDERS = {"M": Gender.MALE, "F": Gender.FEMALE, "O": Gender.OTHER}
_ACCENTS = {
    "MEXICAN": Accent.MEXICAN_SPANISH,
    "COLOMBIAN": Accent.COLOMBIAN_SPANISH,
    "ARGENTINE": Accent.ARGENTINE_SPANISH,
}
_ACCENT_BY_COUNTRY = {
    "MEXICO": Accent.MEXICAN_SPANISH,
    "COLOMBIA": Accent.COLOMBIAN_SPANISH,
    "ARGENTINA": Accent.ARGENTINE_SPANISH,
}
_POINT = re.compile(r"^\s*POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)\s*$", re.I)


def label(value: Any) -> str | None:
    """'IN PROCESS' -> 'In Process', 'POS' stays 'POS', None stays None."""

    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return " ".join(
        word if word.upper() in _ACRONYMS else word.capitalize() for word in text.split(" ")
    )


def proper_name(value: Any) -> str:
    """Names and places arrive in capitals: 'GUILLERMO DIEGO' -> 'Guillermo Diego'."""

    return " ".join(str(value or "").split()).title()


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def branch_number(branch_id: Any) -> int:
    """The app models branches as integers; derive a stable one from the lakehouse text id."""

    if branch_id is None:
        return 0
    return zlib.crc32(str(branch_id).encode()) % 1_000_000


def to_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    return float(value)  # Decimal, int and float all convert the same way


def mask_card_number(value: Any) -> str:
    """Keep only the last four digits (defence in depth: the query already masks)."""

    text = str(value or "")
    return "*" * max(len(text) - 4, 0) + text[-4:]


def parse_point(value: Any) -> tuple[float | None, float | None]:
    """DuckDB POINT_2D arrives as 'POINT (x y)'; the lakehouse stores (latitude longitude)."""

    if value is None:
        return None, None
    match = _POINT.match(str(value))
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def map_customer(row: dict[str, Any], *, loaded_at: datetime) -> Customer:
    country = proper_name(row["country"])
    accent = _ACCENTS.get(str(row.get("detected_accent") or "").upper()) or _ACCENT_BY_COUNTRY.get(
        country.upper(), Accent.ENGLISH
    )
    return Customer(
        customer_id=row["customer_id"],
        document_number=str(row["document_number"]),
        document_type=str(row["document_type"]),
        first_name=proper_name(row["first_name"]),
        last_name=proper_name(row["last_name"]),
        date_of_birth=row["date_of_birth"],
        gender=_GENDERS.get(str(row.get("gender") or "").upper(), Gender.PREFER_NOT_TO_SAY),
        mobile_phone=(row.get("mobile_phone") or None),
        city=proper_name(row["city"]),
        state=proper_name(row["state"]),
        country=country,
        detected_accent=accent,
        segment=label(row["segment"]) or "Basic",
        registration_date=as_utc(row["registration_date"]) or loaded_at,
        registration_branch_id=branch_number(row.get("registration_branch_id")),
        customer_status=label(row["customer_status"]) or "Inactive",
        # Dataset customers are not hackathon judges, so the guided tour is not offered.
        onboarding_completed=True,
        last_updated=loaded_at,
    )


def map_product(row: dict[str, Any], *, loaded_at: datetime) -> Product:
    return Product(
        product_id=row["product_id"],
        customer_id=row["customer_id"],
        product_type=label(row["product_type"]) or "Credit Card",
        product_number=mask_card_number(row["product_number"]),
        currency=str(row["currency"]),
        current_balance=to_float(row["current_balance"], 0.0),
        # Debit cards have no credit limit in the lakehouse.
        credit_limit=to_float(row.get("credit_limit"), 0.0),
        opening_date=row["opening_date"],
        opening_branch_id=branch_number(row.get("opening_branch_id")),
        product_status=label(row["product_status"]) or "Active",
        opening_channel=label(row["opening_channel"]) or "Branch",
        has_linked_app=bool(row["has_linked_app"]),
        last_updated=loaded_at,
    )


def map_transaction(row: dict[str, Any], *, keep_fraud_labels: bool = True) -> Transaction:
    latitude, longitude = parse_point(row.get("transaction_location"))
    transaction_date = as_utc(row["transaction_date"])
    process_date = row.get("process_date")
    return Transaction(
        transaction_id=row["transaction_id"],
        transaction_date=transaction_date,
        process_date=process_date if isinstance(process_date, date) else transaction_date.date(),
        product_id=row["product_id"],
        customer_id=row["customer_id"],
        transaction_type=label(row["transaction_type"]) or "Purchase",
        transaction_category=label(row.get("transaction_category")),
        amount=to_float(row["amount"], 0.0),
        currency=str(row["currency"]),
        amount_usd=to_float(row.get("amount_usd")),
        channel=label(row["channel"]) or "POS",
        branch_id=row.get("branch_id"),
        merchant_name=label(row.get("merchant_name")),
        merchant_category=label(row.get("merchant_category")),
        transaction_country=proper_name(row["transaction_country"]),
        transaction_city=(
            proper_name(row["transaction_city"]) if row.get("transaction_city") else None
        ),
        transaction_status=label(row["transaction_status"]) or "Approved",
        response_code=row.get("response_code"),
        is_fraud=bool(row.get("is_fraud")) if keep_fraud_labels else False,
        fraud_score=to_float(row.get("fraud_score")) if keep_fraud_labels else None,
        latitude=latitude,
        longitude=longitude,
    )


def map_complaint(row: dict[str, Any]) -> Complaint:
    creation_date = as_utc(row["creation_date"])
    process_date = row.get("process_date")
    return Complaint(
        complaint_id=row["complaint_id"],
        creation_date=creation_date,
        process_date=process_date if isinstance(process_date, date) else creation_date.date(),
        customer_id=row["customer_id"],
        case_type=label(row["case_type"]) or "Complaint",
        category=label(row["category"]) or "Other",
        subcategory=label(row.get("subcategory")),
        reception_channel=label(row["reception_channel"]) or "Web",
        affected_product_id=row.get("affected_product_id"),
        related_branch_id=row.get("related_branch_id"),
        origin_interaction_id=row.get("origin_interaction_id"),
        description=str(row["description"]),
        claimed_amount=to_float(row.get("claimed_amount"), 0.0),
        currency=str(row.get("currency") or "USD"),
        priority=label(row["priority"]) or "Medium",
        status=label(row["status"]) or "Open",
        assigned_agent_id=row.get("assigned_agent_id"),
        assignment_date=as_utc(row.get("assignment_date")),
        first_response_date=as_utc(row.get("first_response_date")),
        resolution_date=as_utc(row.get("resolution_date")),
        closing_date=as_utc(row.get("closing_date")),
        sla_breached=bool(row.get("sla_breached")),
        resolution_days=row.get("resolution_days"),
        resolution=row.get("resolution"),
        compensation_granted=to_float(row.get("compensation_granted")),
        resolution_satisfaction=to_float(row.get("resolution_satisfaction")),
        is_repeat_complainer=bool(row.get("is_repeat_complainer")),
    )
