"""`dispute-db-seed-lakehouse` with a fake lakehouse source (synthetic rows only).

Dry runs and argument checks are offline; writes run against the throwaway PostgreSQL from
TEST_POSTGRES_URL and are skipped without it.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

import psycopg
import pytest
from test_lakehouse_mapping import customer_row, transaction_row

from webapp.backend.db import seed_lakehouse
from webapp.backend.db.seed_lakehouse import SeedError, SeedReport, seed

LOADED_AT = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def card_row(product_id: str, customer_id: str) -> dict[str, Any]:
    return {
        "product_id": product_id,
        "customer_id": customer_id,
        "product_type": "CREDIT CARD",
        "product_number": "************" + product_id[-4:].rjust(4, "0"),
        "currency": "COP",
        "current_balance": 0,
        "credit_limit": 1000,
        "opening_date": date(2021, 1, 1),
        "opening_branch_id": "BR-001",
        "product_status": "ACTIVE",
        "opening_channel": "BRANCH",
        "has_linked_app": True,
    }


def complaint_row(complaint_id: str, customer_id: str) -> dict[str, Any]:
    return {
        "complaint_id": complaint_id,
        "creation_date": datetime(2026, 8, 1, 10, 0),
        "process_date": date(2026, 8, 1),
        "customer_id": customer_id,
        "case_type": "CLAIM",
        "category": "CARD PURCHASE",
        "reception_channel": "WEB",
        "description": "Synthetic complaint text.",
        "claimed_amount": 10,
        "currency": "COP",
        "priority": "LOW",
        "status": "OPEN",
    }


class FakeLakehouse:
    """Two customers sharing a phone, three cards, three transactions and two complaints."""

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {
            "customers": [
                customer_row(customer_id="CLI-A", document_number=1001, mobile_phone="+5700"),
                customer_row(customer_id="CLI-B", document_number=1002, mobile_phone="+5700"),
            ],
            "cards": [card_row("PRD-A1", "CLI-A"), card_row("PRD-B1", "CLI-B")],
            "transactions": [
                transaction_row(transaction_id="TRX-A1", customer_id="CLI-A", product_id="PRD-A1"),
                transaction_row(transaction_id="TRX-B1", customer_id="CLI-B", product_id="PRD-B1"),
                # A card the source filtered out of `cards`: the transaction must be skipped.
                transaction_row(
                    transaction_id="TRX-ORPHAN", customer_id="CLI-A", product_id="PRD-GONE"
                ),
            ],
            "complaints": [complaint_row("CMP-A1", "CLI-A"), complaint_row("CMP-B1", "CLI-B")],
        }
        self.limits: list[int | None] = []

    def select_customer_ids(self, limit: int | None) -> list[str]:
        self.limits.append(limit)
        ids = [row["customer_id"] for row in self.rows["customers"]]
        return ids if limit is None else ids[:limit]

    def fetch(self, entity: str, customer_ids: Sequence[str]) -> list[dict[str, Any]]:
        return [row for row in self.rows[entity] if row["customer_id"] in customer_ids]


# ----------------------------------------------------------------------------- offline


def test_default_sample_is_one_hundred_customers():
    assert seed_lakehouse.DEFAULT_CUSTOMERS == 100
    assert seed_lakehouse._parse_args([]).customers == 100


@pytest.mark.parametrize("argv", [["--customers", "0"], ["--chunk-size", "0"]])
def test_non_positive_sizes_are_rejected(argv: list[str]):
    with pytest.raises(SystemExit):
        seed_lakehouse._parse_args(argv)


def test_dry_run_validates_every_row_and_writes_nothing():
    source = FakeLakehouse()

    report = seed(source, None, limit=2, loaded_at=LOADED_AT)

    assert source.limits == [2]
    assert report.customers_selected == 2
    assert report.customers_inserted == 2
    assert report.transactions_inserted == 3
    assert report.transactions_available == 3
    assert report.rows_rejected == 0


def test_malformed_rows_are_counted_instead_of_aborting_the_seed():
    source = FakeLakehouse()
    del source.rows["transactions"][0]["transaction_date"]

    report = seed(source, None, limit=2, loaded_at=LOADED_AT)

    assert report.rows_rejected == 1
    assert report.transactions_inserted == 2


def test_report_warns_when_the_demo_would_have_too_few_transactions():
    small = SeedReport(transactions_available=999)
    enough = SeedReport(transactions_available=seed_lakehouse.MIN_DEMO_TRANSACTIONS)

    assert any(line.startswith("WARNING") for line in small.lines())
    assert not any(line.startswith("WARNING") for line in enough.lines())


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://owner:pw@db.example.com:5432/factored",
        "postgresql://owner:pw@10.0.0.5:5432/factored",
    ],
)
def test_remote_targets_are_refused_unless_explicitly_allowed(url: str):
    with pytest.raises(SeedError, match=r"--allow-remote") as raised:
        seed_lakehouse._check_target(url, allow_remote=False)

    assert "pw" not in str(raised.value)
    seed_lakehouse._check_target(url, allow_remote=True)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_local_targets_are_accepted(host: str):
    seed_lakehouse._check_target(f"postgresql://owner:pw@{host}:5433/factored", allow_remote=False)


# ----------------------------------------------------------------------------- PostgreSQL


def count(url: str, table: str) -> int:
    with psycopg.connect(url) as connection:
        return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_seed_writes_the_sample_and_is_idempotent(clean_postgres):
    with psycopg.connect(clean_postgres.owner_url) as connection:
        first = seed(FakeLakehouse(), connection, limit=2, loaded_at=LOADED_AT)
        second = seed(FakeLakehouse(), connection, limit=2, loaded_at=LOADED_AT)

    assert (first.customers_inserted, first.cards_inserted) == (2, 2)
    assert first.transactions_inserted == 2
    assert first.transactions_skipped == 1  # TRX-ORPHAN has no loaded card
    assert first.complaints_inserted == 2
    assert first.transactions_available == 2

    assert second.customers_inserted == 0
    assert second.customers_already_present == 2
    assert second.transactions_inserted == 0
    assert second.transactions_available == 2

    assert count(clean_postgres.owner_url, "customers") == 2
    assert count(clean_postgres.owner_url, "transactions") == 2


def test_seed_keeps_the_first_owner_of_a_duplicated_phone(clean_postgres):
    with psycopg.connect(clean_postgres.owner_url) as connection:
        report = seed(FakeLakehouse(), connection, limit=2, loaded_at=LOADED_AT)
        phones = dict(
            connection.execute("SELECT customer_id, mobile_phone FROM customers").fetchall()
        )

    assert report.phones_cleared == 1
    assert phones == {"CLI-A": "+5700", "CLI-B": None}


def test_seeded_customers_are_active_for_the_login(clean_postgres):
    with psycopg.connect(clean_postgres.owner_url) as connection:
        seed(FakeLakehouse(), connection, limit=1, loaded_at=LOADED_AT)
        status = connection.execute("SELECT customer_status FROM customers").fetchone()[0]

    assert status == "Active"


def test_hidden_fraud_labels_are_not_loaded(clean_postgres):
    with psycopg.connect(clean_postgres.owner_url) as connection:
        seed(FakeLakehouse(), connection, limit=2, keep_fraud_labels=False, loaded_at=LOADED_AT)
        labels = connection.execute("SELECT DISTINCT is_fraud, fraud_score FROM transactions")

        assert labels.fetchall() == [(False, None)]


def test_seeded_card_numbers_are_masked(clean_postgres):
    with psycopg.connect(clean_postgres.owner_url) as connection:
        seed(FakeLakehouse(), connection, limit=2, loaded_at=LOADED_AT)
        numbers = [row[0] for row in connection.execute("SELECT product_number FROM products")]

    assert numbers
    assert all(number.startswith("************") for number in numbers)
