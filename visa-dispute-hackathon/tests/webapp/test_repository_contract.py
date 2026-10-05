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
from webapp.backend.models.call_center_interaction import CallCenterInteraction
from webapp.backend.models.call_transcript import CallTranscript
from webapp.backend.models.customer import InterfaceLocale, TutorialStatus
from webapp.backend.models.satisfaction_survey import SatisfactionSurvey
from webapp.backend.repositories.interfaces import Repositories
from webapp.backend.repositories.postgres import open_repositories
from webapp.backend.services.complaint_filing import (
    ComplaintFilingService,
    UnsupportedVisaConditionError,
)
from webapp.backend.services.izzy_agent import seed_izzy_agent


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


def test_call_center_records_round_trip_and_update(backend: Backend):
    customer = backend.repos.customers.create(make_customer())
    agent = seed_izzy_agent(backend.repos.service_agents)
    interaction = CallCenterInteraction(
        interaction_id="INT-1",
        interaction_date=NOW,
        process_date=NOW.date(),
        customer_id=customer.customer_id,
        agent_id=agent.agent_id,
        interaction_type="Inbound Call",
        channel="Phone",
        contact_reason="Card dispute support",
        reason_category="Complaint",
        requires_followup=True,
        was_escalated=False,
        has_transcript=False,
        has_recording=False,
    )
    backend.repos.call_center_interactions.create(interaction)
    transcript = CallTranscript(
        transcript_id="TRN-1",
        interaction_id=interaction.interaction_id,
        process_date=NOW.date(),
        customer_id=customer.customer_id,
        agent_id=agent.agent_id,
        full_text="Customer: hello",
        customer_text="hello",
        detected_language="en",
        transcription_model="test-model",
        duration_seconds=1,
    )
    backend.repos.call_transcripts.create(transcript)
    survey = SatisfactionSurvey(
        survey_id="SRV-1",
        survey_date=NOW,
        process_date=NOW.date(),
        interaction_id=interaction.interaction_id,
        customer_id=customer.customer_id,
        agent_id=agent.agent_id,
        survey_type="CSAT",
        send_channel="Phone",
        main_score=5,
    )
    backend.repos.satisfaction_surveys.create(survey)

    assert backend.repos.service_agents.get_by_employee_code(agent.employee_code) == agent
    assert backend.repos.call_center_interactions.list_by_customer(customer.customer_id) == [
        interaction
    ]
    assert (
        backend.repos.call_transcripts.get_by_interaction(interaction.interaction_id) == transcript
    )
    assert backend.repos.satisfaction_surveys.list_by_agent(agent.agent_id) == [survey]

    updated_agent = agent.model_copy(update={"avg_csat": 5.0})
    updated_interaction = interaction.model_copy(update={"was_resolved": True})
    updated_transcript = transcript.model_copy(update={"full_text": "Customer: hello\nAgent: hi"})
    backend.repos.service_agents.update(updated_agent)
    backend.repos.call_center_interactions.update(updated_interaction)
    backend.repos.call_transcripts.update(updated_transcript)

    assert backend.repos.service_agents.get_by_id(agent.agent_id) == updated_agent
    assert (
        backend.repos.call_center_interactions.get_by_id(interaction.interaction_id)
        == updated_interaction
    )
    assert (
        backend.repos.call_transcripts.get_by_interaction(interaction.interaction_id)
        == updated_transcript
    )
    assert seed_izzy_agent(backend.repos.service_agents) == updated_agent


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
    assert customers.get_by_phone("+55 (11) 98102-0050") == customer
    assert customers.get_by_phone("5511981020050") == customer
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


def test_account_registration_replaces_phone_owner_and_owned_data(backend: Backend):
    repositories = backend.repos
    previous_id = "CLI-DEMO-OLD"
    previous_product_id = "PRD-DEMO-OLD"
    replacement_id = "CLI-DEMO-NEW"
    previous = make_customer(previous_id, mobile_phone="+5511981020050")
    previous_card = make_product(previous_product_id, customer_id=previous_id)
    repositories.account_registration.register(previous, previous_card)
    repositories.transactions.create(
        make_transaction(customer_id=previous_id, product_id=previous_product_id)
    )
    repositories.complaints.create(make_complaint(customer_id=previous_id))
    repositories.sessions.create(make_session(customer_id=previous_id))

    replacement = make_customer(
        replacement_id,
        document_number="DOC-C2",
        mobile_phone="+5511981020050",
    )
    replacement_card = make_product("PRD-DEMO-NEW", customer_id=replacement_id)
    repositories.account_registration.register(replacement, replacement_card)

    assert repositories.customers.get_by_id(previous_id) is None
    assert repositories.products.list_by_customer(previous_id) == []
    assert repositories.transactions.list_by_customer(previous_id) == []
    assert repositories.complaints.list_by_customer(previous_id) == []
    assert repositories.sessions.get("sess-1") is None
    assert repositories.customers.get_by_phone("5511981020050") == replacement
    assert repositories.products.list_by_customer(replacement_id) == [replacement_card]


def test_failed_account_replacement_is_atomic(backend: Backend):
    repositories = backend.repos
    previous_id = "CLI-DEMO-OLD"
    previous_product = make_product("PRD-DEMO-OLD", customer_id=previous_id)
    previous = make_customer(previous_id, mobile_phone="+5511981020050")
    repositories.account_registration.register(previous, previous_product)
    repositories.customers.create(
        make_customer("C2", document_number="CONFLICT", mobile_phone="+573001112233")
    )

    replacement = make_customer(
        "CLI-DEMO-NEW",
        document_number="CONFLICT",
        mobile_phone="+5511981020050",
    )
    with pytest.raises(ValueError, match=r"FACTORED_ID already exists."):
        repositories.account_registration.register(
            replacement,
            make_product("PRD-DEMO-NEW", customer_id="CLI-DEMO-NEW"),
        )

    assert repositories.customers.get_by_id(previous_id) == previous
    assert repositories.products.list_by_customer(previous_id) == [previous_product]
    assert repositories.customers.get_by_id("CLI-DEMO-NEW") is None


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
    assert complaints.get_by_origin_interaction("C1", "missing") is None

    escalated = resolved.model_copy(update={"status": "Escalated"})
    complaints.update(escalated)
    assert complaints.get_by_id("K-resolved") == escalated


def test_update_of_an_unknown_complaint_fails(backend: Backend):
    with pytest.raises(ValueError, match=r"Complaint does not exist."):
        backend.repos.complaints.update(make_complaint("ghost"))


def test_duplicate_complaint_id_is_rejected(backend: Backend):
    backend.repos.customers.create(make_customer("C1"))
    backend.repos.complaints.create(make_complaint("K-duplicate"))

    with pytest.raises(ValueError, match="Complaint already exists"):
        backend.repos.complaints.create(make_complaint("K-duplicate"))


def test_call_center_complaint_filing_contract_is_idempotent(backend: Backend):
    backend.repos.customers.create(make_customer("C1"))
    transaction = make_transaction(
        "T-VOICE",
        merchant_name="Lemon Drop Market",
        channel="E-commerce",
        amount=12.49,
    )
    service = ComplaintFilingService(backend.repos.complaints)

    filed = service.file_from_call(
        call_id="rtc-demo-call",
        customer_id="C1",
        transaction=transaction,
        visa_condition_code="10.4",
        now=NOW,
    )
    repeated = service.file_from_call(
        call_id="rtc-demo-call",
        customer_id="C1",
        transaction=transaction,
        visa_condition_code="10.4",
        now=NOW + timedelta(minutes=1),
    )

    assert repeated == filed
    assert len(backend.repos.complaints.list_by_customer("C1")) == 1
    assert filed.customer_id == "C1"
    assert filed.case_type == "Claim"
    assert filed.category == "Card Purchase"
    assert filed.subcategory == "Visa 10.4 · Other Fraud — Card-Absent Environment"
    assert filed.reception_channel == "Call Center"
    assert filed.affected_product_id == "P1"
    assert filed.origin_interaction_id == "rtc-demo-call"
    assert filed.claimed_amount == 12.49
    assert filed.currency == "USD"
    assert filed.priority == "High"
    assert filed.status == "In Review"
    assert filed.assigned_agent_id == "IZZY"
    assert filed.assignment_date == NOW
    assert filed.first_response_date == NOW
    assert "Candidate Visa condition: 10.4" in filed.description
    assert backend.repos.complaints.get_by_origin_interaction("C1", "rtc-demo-call") == filed


def test_complaint_filing_rejects_an_unsupported_visa_condition(backend: Backend):
    service = ComplaintFilingService(backend.repos.complaints)

    with pytest.raises(UnsupportedVisaConditionError, match="unsupported Visa condition"):
        service.file_from_call(
            call_id="rtc-unsupported",
            customer_id="C1",
            transaction=make_transaction(),
            visa_condition_code="99.9",
            now=NOW,
        )


@pytest.mark.parametrize(
    ("visa_code", "expected_subcategory", "expected_priority"),
    [
        (
            "10.3",
            "Visa 10.3 · Other Fraud — Card-Present Environment",
            "High",
        ),
        (
            "10.4",
            "Visa 10.4 · Other Fraud — Card-Absent Environment",
            "High",
        ),
        ("12.6.1", "Visa 12.6.1 · Duplicate Processing", "Medium"),
    ],
)
def test_complaint_filing_maps_supported_visa_codes(
    backend: Backend,
    visa_code: str,
    expected_subcategory: str,
    expected_priority: str,
):
    backend.repos.customers.create(make_customer("C1"))
    service = ComplaintFilingService(backend.repos.complaints)

    complaint = service.file_from_call(
        call_id=f"rtc-{visa_code}",
        customer_id="C1",
        transaction=make_transaction(channel="POS"),
        visa_condition_code=visa_code,
        now=NOW,
    )

    assert complaint.subcategory == expected_subcategory
    assert complaint.priority == expected_priority


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


# ----------------------------------------------------------------------------- card purchases


def test_card_purchases_join_the_card_and_keep_only_the_customers_purchases(backend: Backend):
    backend.repos.customers.create(make_customer("C1"))
    backend.repos.customers.create(make_customer("C2"))
    backend.repos.products.create(make_product("P1", "C1", product_number="4111222233334444"))
    backend.repos.products.create(make_product("P2", "C2"))
    backend.repos.transactions.create(make_transaction("T-buy", transaction_type="Purchase"))
    backend.repos.transactions.create(
        make_transaction("T-cash", transaction_type="Withdrawal", transaction_date=NOW)
    )
    backend.repos.transactions.create(
        make_transaction("T-other", "C2", "P2", transaction_type="Purchase")
    )
    purchases = backend.repos.card_purchases

    found = purchases.list_by_customer("C1")

    assert [item.transaction.transaction_id for item in found] == ["T-buy"]
    assert (found[0].card_type, found[0].card_last_four) == ("Credit Card", "4444")
    assert purchases.get_for_customer("C1", "T-buy") is not None
    assert purchases.get_for_customer("C1", "T-other") is None
    assert purchases.get_for_customer("C1", "T-cash") is None
