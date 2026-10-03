"""The same behavioural contract, asserted against the in-memory test double AND PostgreSQL.

The PostgreSQL parametrisation runs when TEST_POSTGRES_URL points at a server (for example the
docker-compose database) and is skipped otherwise, so the suite stays runnable offline.
"""

import threading
from dataclasses import dataclass
from datetime import timedelta

import pytest
from factories import (
    NOW,
    make_complaint,
    make_customer,
    make_product,
    make_session,
    make_transaction,
)
from fakes import new_repositories

from webapp.backend.config import Settings
from webapp.backend.models.customer import InterfaceLocale, TutorialStatus
from webapp.backend.repositories.interfaces import Repositories
from webapp.backend.repositories.postgres import open_repositories


@dataclass
class Backend:
    name: str
    repos: Repositories


@pytest.fixture(params=["in_memory", "postgres"])
def backend(request: pytest.FixtureRequest):
    if request.param == "in_memory":
        yield Backend("in_memory", new_repositories())
        return
    database = request.getfixturevalue("clean_postgres")
    repos = open_repositories(Settings(_env_file=None, database_url=database.app_url))
    try:
        yield Backend("postgres", repos)
    finally:
        repos.close()


# ----------------------------------------------------------------------------- customers


def test_customer_round_trips_through_every_lookup(backend: Backend):
    customers = backend.repos.customers
    customer = make_customer(
        mobile_phone="+5511981020050",
        preferred_locale=InterfaceLocale.PORTUGUESE,
        tutorial_status=TutorialStatus.IN_PROGRESS,
        tutorial_last_completed_step="cards",
        onboarding_completed=True,
        tutorial_version=4,
    )

    customers.create(customer)

    assert customers.get_by_id("C1") == customer
    assert customers.get_by_document("DOC-C1") == customer
    assert customers.get_by_phone("+5511981020050") == customer
    assert customers.get_by_id("missing") is None
    assert customers.get_by_document("missing") is None
    assert customers.get_by_phone("+000") is None


def test_duplicate_document_or_phone_is_rejected_and_not_stored(backend: Backend):
    customers = backend.repos.customers
    customers.create(make_customer("C1", mobile_phone="+1555"))

    with pytest.raises(ValueError, match=r"FACTORED_ID already exists."):
        customers.create(make_customer("C2", document_number="DOC-C1"))
    with pytest.raises(ValueError, match=r"Phone number already exists."):
        customers.create(make_customer("C3", mobile_phone="+1555"))

    assert customers.get_by_id("C2") is None
    assert customers.get_by_id("C3") is None


def test_customers_without_a_phone_can_coexist(backend: Backend):
    customers = backend.repos.customers

    customers.create(make_customer("C1"))
    customers.create(make_customer("C2"))

    assert customers.get_by_id("C1") is not None
    assert customers.get_by_id("C2") is not None


def test_concurrent_signups_with_the_same_document_create_exactly_one_customer(backend: Backend):
    customers = backend.repos.customers
    outcomes: list[str] = []

    def attempt(index: int) -> None:
        try:
            customers.create(make_customer(f"C{index}", document_number="SAME-DOC"))
            outcomes.append("created")
        except ValueError:
            outcomes.append("rejected")

    threads = [threading.Thread(target=attempt, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["created"] + ["rejected"] * 7


def test_update_persists_profile_and_tutorial_progress(backend: Backend):
    customers = backend.repos.customers
    customer = make_customer()
    customers.create(customer)
    updated = customer.model_copy(
        update={
            "first_name": "Ana Júlia",
            "mobile_phone": "+5511900001001",
            "preferred_locale": InterfaceLocale.MEXICAN_SPANISH,
            "tutorial_status": TutorialStatus.COMPLETED,
            "tutorial_version": 4,
            "onboarding_completed": True,
            "last_updated": NOW + timedelta(minutes=5),
        }
    )

    customers.update(updated)

    assert customers.get_by_id("C1") == updated
    assert customers.get_by_phone("+5511900001001") == updated


def test_update_of_an_unknown_customer_fails(backend: Backend):
    with pytest.raises(ValueError, match=r"Customer does not exist."):
        backend.repos.customers.update(make_customer("ghost"))


def test_name_search_ignores_case_and_accents_and_is_sorted(backend: Backend):
    customers = backend.repos.customers
    customers.create(make_customer("C1", first_name="José María", last_name="Pérez López"))
    customers.create(make_customer("C2", first_name="Jose", last_name="Alvarez"))
    customers.create(make_customer("C3", first_name="Ximena", last_name="Hernández Ruiz"))

    def ids(query: str, **options) -> list[str]:
        return [c.customer_id for c in customers.search_by_full_name(query, **options)]

    assert ids("JOSE MARIA") == ["C1"]
    assert ids("josé") == ["C2", "C1"]
    assert ids("hernandez") == ["C3"]
    assert ids("  perez   lopez ") == ["C1"]
    assert ids("") == ["C2", "C1", "C3"]
    assert ids("", limit=2) == ["C2", "C1"]
    assert ids("nobody") == []


@pytest.mark.parametrize(
    "hostile_query",
    ["%", "_", "\\", "' OR '1'='1", "'; DROP TABLE customers; --", "Ana%' --", "ana\x00"],
)
def test_name_search_treats_wildcards_and_sql_as_plain_text(backend: Backend, hostile_query: str):
    customers = backend.repos.customers
    customers.create(make_customer("C1"))

    try:
        found = customers.search_by_full_name(hostile_query)
    except ValueError:  # a driver may refuse NUL bytes outright; it must never run them as SQL
        found = []

    assert found == []
    assert customers.get_by_id("C1") is not None


# ----------------------------------------------------------------------------- products


def test_products_are_scoped_to_their_customer_and_updatable(backend: Backend):
    backend.repos.customers.create(make_customer("C1"))
    backend.repos.customers.create(make_customer("C2"))
    products = backend.repos.products
    products.create(make_product("P1", "C1"))
    products.create(make_product("P2", "C2", product_number="5500000000000004"))

    assert products.get_by_id("P1") == make_product("P1", "C1")
    assert [p.product_id for p in products.list_by_customer("C1")] == ["P1"]
    assert [p.product_id for p in products.list_by_customer("C2")] == ["P2"]
    assert products.list_by_customer("nobody") == []
    assert products.get_by_id("missing") is None

    blocked = make_product("P1", "C1", product_status="Blocked", last_updated=NOW + timedelta(1))
    products.update(blocked)
    assert products.get_by_id("P1") == blocked


def test_update_of_an_unknown_product_fails(backend: Backend):
    with pytest.raises(ValueError, match=r"Product does not exist."):
        backend.repos.products.update(make_product("ghost"))


# ----------------------------------------------------------------------------- transactions


def test_transactions_are_newest_first_scoped_and_keep_optional_fields(backend: Backend):
    backend.repos.customers.create(make_customer("C1"))
    backend.repos.customers.create(make_customer("C2"))
    backend.repos.products.create(make_product("P1", "C1"))
    backend.repos.products.create(make_product("P2", "C2"))
    transactions = backend.repos.transactions
    old = make_transaction("T-old", transaction_date=NOW - timedelta(days=7))
    new = make_transaction(
        "T-new",
        transaction_date=NOW,
        merchant_name="Shady Business",
        merchant_category="Online Retail",
        amount_usd=129.9,
        fraud_score=0.94,
        is_fraud=True,
        latitude=27.7172,
        longitude=85.324,
        response_code="00",
        branch_id="B-1",
    )
    transactions.create(old)
    transactions.create(new)
    transactions.create(make_transaction("T-other", "C2", "P2"))

    assert [t.transaction_id for t in transactions.list_by_customer("C1")] == ["T-new", "T-old"]
    assert transactions.get_by_id("T-new") == new
    assert transactions.get_by_id("T-old") == old
    assert transactions.list_by_customer("nobody") == []

    reviewed = new.model_copy(update={"transaction_status": "Reversed"})
    transactions.update(reviewed)
    assert transactions.get_by_id("T-new") == reviewed


def test_update_of_an_unknown_transaction_fails(backend: Backend):
    with pytest.raises(ValueError, match=r"Transaction does not exist."):
        backend.repos.transactions.update(make_transaction("ghost"))


# ----------------------------------------------------------------------------- complaints


def test_complaints_are_newest_first_scoped_and_keep_resolution_fields(backend: Backend):
    backend.repos.customers.create(make_customer("C1"))
    backend.repos.customers.create(make_customer("C2"))
    complaints = backend.repos.complaints
    resolved = make_complaint(
        "K-resolved",
        creation_date=NOW - timedelta(days=45),
        status="Resolved",
        assigned_agent_id="IZZY",
        assignment_date=NOW - timedelta(days=45) + timedelta(hours=1),
        resolution_date=NOW - timedelta(days=43),
        closing_date=NOW - timedelta(days=42),
        resolution_days=2,
        resolution="Duplicate charge confirmed.",
        compensation_granted=8.75,
        resolution_satisfaction=5.0,
        is_repeat_complainer=True,
        affected_product_id="P1",
    )
    complaints.create(resolved)
    complaints.create(make_complaint("K-open", creation_date=NOW))
    complaints.create(make_complaint("K-other", "C2"))

    assert [c.complaint_id for c in complaints.list_by_customer("C1")] == ["K-open", "K-resolved"]
    assert complaints.get_by_id("K-resolved") == resolved
    assert complaints.get_by_id("missing") is None

    escalated = resolved.model_copy(update={"status": "Escalated"})
    complaints.update(escalated)
    assert complaints.get_by_id("K-resolved") == escalated


def test_update_of_an_unknown_complaint_fails(backend: Backend):
    with pytest.raises(ValueError, match=r"Complaint does not exist."):
        backend.repos.complaints.update(make_complaint("ghost"))


# ----------------------------------------------------------------------------- sessions


def test_session_lifecycle(backend: Backend):
    backend.repos.customers.create(make_customer("C1"))
    sessions = backend.repos.sessions
    session = make_session("opaque-session-id")

    sessions.create(session)

    assert sessions.get("opaque-session-id") == session
    assert sessions.get("another-id") is None
    sessions.delete("opaque-session-id")
    assert sessions.get("opaque-session-id") is None
    sessions.delete("opaque-session-id")  # deleting twice is harmless
    sessions.delete("never-existed")
