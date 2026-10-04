"""Card purchases from the lakehouse + PostgreSQL, and Izzy's up-to-three purchase options.

Synthetic data only. The lakehouse is replaced by in-memory sources so tests run offline.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta

import fakes
import psycopg
import pytest
from fakes import (
    InMemoryCardPurchaseRepository,
    InMemoryProductRepository,
    InMemoryTransactionRepository,
    clear_repositories,
    demo_card_product_id,
    demo_fruit_transactions,
    new_repositories,
    seed_demo_card,
    seed_demo_customers,
)
from fastapi.testclient import TestClient
from test_izzy_chat import GABRIEL, PHONE, ScriptedClassifier, ScriptedReplies, run_turn, turn

from dispute_agent.jev_decision import JevVoiceRouter
from dispute_agent.transaction_search import RepositoryTransactionSearch, TransactionSearchCriteria
from dispute_agent.voice_call import VoiceCallService, voice_repository_arguments
from dispute_agent.web_chat import ChatTurnInterpreter, IzzyWebChat, WebChatDisputeService
from webapp.backend.config import Settings
from webapp.backend.db.motherduck import LakehouseUnavailableError
from webapp.backend.main import app
from webapp.backend.models.card_transaction import CardTransaction
from webapp.backend.repositories.card_purchases import (
    CombinedCardPurchaseRepository,
    LakehouseCardPurchaseReader,
    card_transaction_from_lakehouse_row,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def purchase(transaction_id: str, customer_id: str = GABRIEL, *, source: str, **overrides):
    base = demo_fruit_transactions(customer_id)[0].model_copy(
        update={"transaction_id": transaction_id, **overrides}
    )
    return CardTransaction(
        transaction=base,
        card_type="Credit Card",
        card_last_four="9999",
        card_status="Active",
        source=source,
    )


class FakeLakehouse:
    def __init__(self, items=(), *, error: Exception | None = None, delay: float = 0.0):
        self.items = list(items)
        self.error = error
        self.delay = delay
        self.calls = 0

    def list_by_customer(self, customer_id, *, limit=500):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return list(self.items)[:limit]

    def get_for_customer(self, customer_id, transaction_id):
        return next((i for i in self.items if i.transaction.transaction_id == transaction_id), None)


class FakePostgres(FakeLakehouse):
    pass


# ----------------------------------------------------------------------------- combined reader


def test_both_sources_are_merged_and_postgres_wins_on_duplicates():
    lakehouse = FakeLakehouse(
        [
            purchase("T-SHARED", source="lakehouse", amount=10.0),
            purchase("T-OLD", source="lakehouse", transaction_date=NOW - timedelta(days=30)),
        ]
    )
    postgres = FakePostgres([purchase("T-SHARED", source="postgres", amount=99.0)])

    merged = CombinedCardPurchaseRepository(postgres, lakehouse).list_by_customer(GABRIEL)

    by_id = {item.transaction.transaction_id: item for item in merged}
    assert set(by_id) == {"T-SHARED", "T-OLD"}
    assert by_id["T-SHARED"].source == "postgres"
    assert by_id["T-SHARED"].transaction.amount == 99.0


def test_another_customers_rows_from_the_lakehouse_are_discarded():
    lakehouse = FakeLakehouse([purchase("T-OTHER", "SOMEONE-ELSE", source="lakehouse")])

    combined = CombinedCardPurchaseRepository(FakePostgres(), lakehouse)

    assert combined.list_by_customer(GABRIEL) == []


@pytest.mark.parametrize(
    "error",
    [LakehouseUnavailableError("down"), psycopg.OperationalError("network")],
)
def test_lakehouse_failure_falls_back_to_postgres(error):
    postgres = FakePostgres([purchase("T-PG", source="postgres")])

    combined = CombinedCardPurchaseRepository(postgres, FakeLakehouse(error=error))

    assert [i.transaction.transaction_id for i in combined.list_by_customer(GABRIEL)] == ["T-PG"]


def test_slow_lakehouse_times_out_and_postgres_still_answers():
    postgres = FakePostgres([purchase("T-PG", source="postgres")])
    slow = FakeLakehouse([purchase("T-LH", source="lakehouse")], delay=0.5)

    combined = CombinedCardPurchaseRepository(postgres, slow, timeout_seconds=0.05)

    assert [i.transaction.transaction_id for i in combined.list_by_customer(GABRIEL)] == ["T-PG"]


def test_lakehouse_history_is_cached_per_customer():
    lakehouse = FakeLakehouse([purchase("T-LH", source="lakehouse")])
    combined = CombinedCardPurchaseRepository(FakePostgres(), lakehouse, cache_seconds=60)

    combined.list_by_customer(GABRIEL)
    combined.list_by_customer(GABRIEL)

    assert lakehouse.calls == 1


def test_without_a_token_only_postgres_is_used():
    combined = CombinedCardPurchaseRepository.from_settings(
        FakePostgres(), Settings(_env_file=None, motherduck_token=None)
    )

    assert combined.lakehouse is None


def test_lookup_by_id_is_scoped_to_the_customer():
    lakehouse = FakeLakehouse([purchase("T-LH", source="lakehouse")])
    combined = CombinedCardPurchaseRepository(FakePostgres(), lakehouse)

    assert combined.get_for_customer(GABRIEL, "T-LH").source == "lakehouse"
    assert combined.get_for_customer(GABRIEL, "UNKNOWN") is None


def test_only_card_purchases_are_considered():
    transactions = InMemoryTransactionRepository()
    products = InMemoryProductRepository()
    seed_demo_card(products, GABRIEL)
    fruit = demo_fruit_transactions(GABRIEL)
    transactions.create(fruit[0])
    transactions.create(fruit[1].model_copy(update={"transaction_type": "Withdrawal"}))
    transactions.create(fruit[2].model_copy(update={"transaction_type": "Transfer"}))

    found = InMemoryCardPurchaseRepository(transactions, products).list_by_customer(GABRIEL)

    assert [i.transaction.transaction_id for i in found] == [fruit[0].transaction_id]


def test_lakehouse_rows_keep_only_the_last_four_card_digits():
    row = {
        **{
            key: value
            for key, value in demo_fruit_transactions(GABRIEL)[0].model_dump().items()
            if key not in {"latitude", "longitude"}
        },
        "transaction_type": "PURCHASE",
        "channel": "POS",
        "transaction_location": None,
        "card_type": "CREDIT CARD",
        "card_last_four": "4444",
        "card_status": "ACTIVE",
    }

    item = card_transaction_from_lakehouse_row(row)

    assert (item.card_type, item.card_last_four, item.card_status) == (
        "Credit Card",
        "4444",
        "Active",
    )
    assert item.transaction.transaction_type == "Purchase"


def test_lakehouse_query_is_scoped_parameterised_and_never_reads_full_card_numbers():
    reader = LakehouseCardPurchaseReader(
        Settings(_env_file=None, motherduck_token="test-only"), connect=lambda: None
    )

    query = reader._select(" LIMIT %s")

    assert "t.customer_id = %s" in query
    assert "t.transaction_type = 'PURCHASE'" in query
    assert "right(p.product_number, 4) AS card_last_four" in query
    assert query.count("product_number") == 1  # only inside right(..., 4)


# ----------------------------------------------------------------------------- chat options


@pytest.fixture
def chat_with_purchases():
    repositories = new_repositories()
    seed_demo_customers(repositories.customers)
    seed_demo_card(repositories.products, GABRIEL)
    for item in demo_fruit_transactions(GABRIEL):
        repositories.transactions.create(item)
    classifier = ScriptedClassifier()
    chat = IzzyWebChat(
        WebChatDisputeService.from_repositories(repositories),
        ChatTurnInterpreter(jev_router=JevVoiceRouter(api_key=""), structured_model=classifier),
        phone_number=PHONE,
        session_ttl_seconds=1800,
        max_message_chars=500,
        max_turns=40,
        reply_model=ScriptedReplies(),
    )
    customer = repositories.customers.get_by_id(GABRIEL)
    session = chat.open_session(customer, locale="en-US").session_id
    return chat, repositories, classifier, session


def options_of(events):
    return next(event for event in events if event["event"] == "options")["options"]


def tap(chat, session, **action):
    async def collect():
        return [event async for event in chat.stream_turn(session, GABRIEL, "", **action)]

    return asyncio.run(collect())


def test_an_ambiguous_description_offers_at_most_three_options(chat_with_purchases):
    chat, _, classifier, session = chat_with_purchases

    classifier.queue.append(turn("describe_transaction", merchant_query="market"))
    events, text = run_turn(chat, session, "a market purchase")

    offered = options_of(events)
    assert 2 <= len(offered) <= 3
    assert all(option["card_last_four"] == "9999" for option in offered)
    assert f"I found {len(offered)} purchases" in text


def test_a_category_alone_is_enough_to_search(chat_with_purchases):
    chat, _, classifier, session = chat_with_purchases

    classifier.queue.append(turn("describe_transaction", category="fruit"))
    events, _ = run_turn(chat, session, "a fruit purchase")

    assert 1 <= len(options_of(events)) <= 3


def test_tapping_an_option_selects_it_and_stores_it_in_the_agent_state(chat_with_purchases):
    chat, _, classifier, session = chat_with_purchases
    classifier.queue.append(turn("describe_transaction", merchant_query="market"))
    offered = options_of(run_turn(chat, session, "a market purchase")[0])

    events = tap(chat, session, selected_transaction_id=offered[1]["transaction_id"])

    state = chat.service.get(session)
    assert state.stage.value == "needs_dispute_classification"
    assert state.confirmed_transaction.transaction_id == offered[1]["transaction_id"]
    assert {"event": "selected", "transaction_id": offered[1]["transaction_id"]} in events


def test_choosing_by_number_in_text_selects_that_option(chat_with_purchases):
    chat, _, classifier, session = chat_with_purchases
    classifier.queue.append(turn("describe_transaction", merchant_query="market"))
    offered = options_of(run_turn(chat, session, "a market purchase")[0])

    classifier.queue.append(turn("select_option", option_number=2))
    run_turn(chat, session, "the second one")

    assert (
        chat.service.get(session).confirmed_transaction.transaction_id
        == (offered[1]["transaction_id"])
    )


def test_a_purchase_that_was_not_offered_cannot_be_selected(chat_with_purchases):
    chat, _, classifier, session = chat_with_purchases
    classifier.queue.append(turn("describe_transaction", merchant_query="mango gold"))
    run_turn(chat, session, "Mango Gold")

    tap(chat, session, selected_transaction_id="FRUIT-01-LEMON")

    state = chat.service.get(session)
    assert state.stage.value == "confirm_transaction"
    assert state.confirmed_transaction is None


def test_none_of_these_excludes_the_options_and_asks_for_more_detail(chat_with_purchases):
    chat, _, classifier, session = chat_with_purchases
    classifier.queue.append(turn("describe_transaction", merchant_query="market"))
    offered = options_of(run_turn(chat, session, "a market purchase")[0])

    tap(chat, session, reject_options=True)

    state = chat.service.get(session)
    assert state.stage.value == "needs_transaction_details"
    assert {option["transaction_id"] for option in offered} <= set(state.rejected_transaction_ids)


def test_a_purchase_only_in_the_lakehouse_is_copied_to_postgres_when_selected():
    repositories = new_repositories()
    seed_demo_customers(repositories.customers)
    seed_demo_card(repositories.products, GABRIEL)
    lakehouse_only = purchase(
        "LH-ONLY-1",
        source="lakehouse",
        product_id=demo_card_product_id(GABRIEL),
        merchant_name="Lakehouse Bistro",
    )
    combined = CombinedCardPurchaseRepository(
        repositories.card_purchases, FakeLakehouse([lakehouse_only])
    )
    service = WebChatDisputeService.from_repositories(repositories, purchases=combined)
    customer = repositories.customers.get_by_id(GABRIEL)
    service.start_session("s1", customer, locale="en-US")

    selected = service.select_known_transaction("s1", "LH-ONLY-1")

    assert selected is not None
    assert repositories.transactions.get_by_id("LH-ONLY-1") is not None
    assert service.get("s1").confirmed_transaction.transaction_id == "LH-ONLY-1"


# ----------------------------------------------------------------------------- one database


def test_a_card_blocked_by_the_voice_agent_shows_as_blocked_in_the_app():
    """PM rule: app, chat and voice share one database; a voice block reflects in the app."""

    seed_demo_customers(fakes.customer_repository)
    seed_demo_card(fakes.product_repository, GABRIEL)
    for item in demo_fruit_transactions(GABRIEL):
        fakes.transaction_repository.create(item)
    arguments = voice_repository_arguments(fakes.repositories)
    arguments["transaction_repository"] = RepositoryTransactionSearch(fakes.transaction_repository)
    calls = VoiceCallService(fakes.customer_repository, **arguments)
    try:
        state = calls.start("+5511981020050", call_id="voice-block")
        calls.confirm_language(state.call_id)
        calls.choose_authentication_method(state.call_id, method="phone")
        calls.search_transactions(
            state.call_id, TransactionSearchCriteria(merchant_query="mango gold")
        )
        calls.resolve_transaction_candidate(state.call_id, confirmed=True)
        calls.classify_dispute(
            state.call_id,
            allegation="UNAUTHORIZED_CARD",
            customer_denies_authorization=True,
            customer_reported_card_environment="CARD_ABSENT",
        )

        client = TestClient(app)
        assert client.post("/api/auth/login", json={"factored_id": "123456"}).status_code == 200
        cards = client.get("/api/products").json()

        assert [card["product_status"] for card in cards] == ["Blocked"]
    finally:
        clear_repositories()


@pytest.mark.parametrize(
    "message",
    ["in 2025", "ayer", "el mes pasado", "on 15/09", "la semana pasada", "em setembro"],
)
def test_typed_date_evidence_accepts_years_and_periods(message):
    from dispute_agent.web_chat.search import typed_date_evidence

    assert typed_date_evidence(message) is True


@pytest.mark.parametrize("message", ["Mango Gold store", "about 50 dollars", "the second one"])
def test_typed_date_evidence_rejects_text_without_dates(message):
    from dispute_agent.web_chat.search import typed_date_evidence

    assert typed_date_evidence(message) is False
