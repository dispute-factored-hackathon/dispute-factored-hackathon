"""Safe, customer-scoped SQLite search for the synthetic voice demo."""

from __future__ import annotations

import json
import logging
import math
import random
import sqlite3
import time
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from webapp.backend.models.transaction import Transaction

LOGGER = logging.getLogger(__name__)

DEFAULT_DEMO_CUSTOMER_ID = "DEMO-BR-GABRIEL-123456"
MAX_RESULTS = 10
AMOUNT_TOLERANCE_RATE = 0.10
MIN_AMOUNT_TOLERANCE = 5.0
MIN_RELEVANCE_SCORE = 0.35
TRANSACTION_FILTER_FIELDS = (
    "merchant_query",
    "approximate_amount",
    "currency",
    "date_from",
    "date_to",
    "country",
    "city",
    "channel",
    "transaction_type",
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
    "latitude",
    "longitude",
)


class InsufficientTransactionCriteriaError(ValueError):
    """Raised when a search would be too broad for the voice journey."""


@dataclass(frozen=True)
class TransactionSearchCriteria:
    """Schema-constrained filters extracted from the caller's description."""

    merchant_query: str | None = None
    approximate_amount: float | None = None
    currency: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    country: str | None = None
    city: str | None = None
    channel: str | None = None
    transaction_type: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> TransactionSearchCriteria:
        """Validate model tool arguments before they can influence SQL."""

        def text(name: str, *, maximum: int = 120) -> str | None:
            value = values.get(name)
            if value is None:
                return None
            normalized = " ".join(str(value).split())
            if not normalized:
                return None
            if len(normalized) > maximum:
                raise ValueError(f"{name} is too long")
            return normalized

        def parsed_date(name: str) -> date | None:
            value = text(name, maximum=10)
            if value is None:
                return None
            try:
                return date.fromisoformat(value)
            except ValueError as error:
                raise ValueError(f"{name} must use YYYY-MM-DD") from error

        amount_value = values.get("approximate_amount")
        amount = None
        if amount_value is not None:
            try:
                amount = float(amount_value)
            except (TypeError, ValueError) as error:
                raise ValueError("approximate_amount must be numeric") from error
            if not math.isfinite(amount) or amount <= 0:
                raise ValueError("approximate_amount must be positive and finite")

        merchant_query = text("merchant_query")
        country = text("country", maximum=80)
        city = text("city", maximum=80)
        criteria = cls(
            merchant_query=(_canonical_merchant_query(merchant_query) if merchant_query else None),
            approximate_amount=amount,
            currency=text("currency", maximum=3),
            date_from=parsed_date("date_from"),
            date_to=parsed_date("date_to"),
            country=_canonical_location(country) if country else None,
            city=_canonical_location(city) if city else None,
            channel=text("channel", maximum=40),
            transaction_type=text("transaction_type", maximum=60),
        )
        if criteria.date_from and criteria.date_to and criteria.date_from > criteria.date_to:
            raise ValueError("date_from cannot be after date_to")
        return criteria

    def merged_with(self, newer: TransactionSearchCriteria) -> TransactionSearchCriteria:
        """Preserve previously supplied details while accepting corrections."""

        updates = {
            field.name: getattr(newer, field.name)
            for field in fields(self)
            if getattr(newer, field.name) is not None
        }
        return replace(self, **updates)

    def without(self, field_names: Iterable[str]) -> TransactionSearchCriteria:
        """Return criteria with explicitly selected filters removed."""
        requested = tuple(dict.fromkeys(field_names))
        unknown = set(requested).difference(TRANSACTION_FILTER_FIELDS)
        if unknown:
            raise ValueError(f"unsupported transaction filter: {sorted(unknown)[0]}")
        return replace(self, **dict.fromkeys(requested))

    def active_filters(self) -> tuple[tuple[str, Any], ...]:
        """Expose active, schema-approved filters for explanations and telemetry."""
        return tuple(
            (name, getattr(self, name))
            for name in TRANSACTION_FILTER_FIELDS
            if getattr(self, name) is not None
        )

    @property
    def has_any_filter(self) -> bool:
        return any(getattr(self, field.name) is not None for field in fields(self))

    @property
    def is_discriminative(self) -> bool:
        return any(
            (
                self.merchant_query,
                self.approximate_amount is not None,
                self.date_from,
                self.date_to,
                self.country,
                self.city,
            )
        )


@dataclass(frozen=True)
class RankedTransaction:
    """One retrieved transaction with an explainable relevance score."""

    transaction: Transaction
    score: float
    matched_fields: tuple[str, ...]


@dataclass(frozen=True)
class TransactionSearchResult:
    criteria: TransactionSearchCriteria
    ranked_transactions: tuple[RankedTransaction, ...]
    sql: str
    retrieved_count: int
    latency_ms: float

    @property
    def transactions(self) -> tuple[Transaction, ...]:
        """Keep callers independent from ranker metadata."""

        return tuple(item.transaction for item in self.ranked_transactions)


class TransactionSearchRepository(Protocol):
    """Replaceable backend boundary for the call transaction-search workflow."""

    def search(
        self,
        customer_id: str,
        criteria: TransactionSearchCriteria,
        *,
        excluded_transaction_ids: tuple[str, ...] = (),
        limit: int = MAX_RESULTS,
    ) -> TransactionSearchResult: ...


class SQLiteTransactionSearchRepository:
    """Read-only query adapter backed by a replaceable SQLite connection."""

    def __init__(
        self,
        database: str | Path = ":memory:",
        *,
        transactions: Iterable[Transaction] | None = None,
        seed_customer_id: str = DEFAULT_DEMO_CUSTOMER_ID,
        location_seed: int = 19,
    ) -> None:
        self.database = str(database)
        self._connection = sqlite3.connect(self.database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.create_function(
            "normalize_text",
            1,
            _normalize_text,
            deterministic=True,
        )
        self._lock = RLock()
        self._create_schema()
        seed = tuple(transactions or demo_fruit_transactions(seed_customer_id, location_seed))
        self._seed(seed)
        self._connection.execute("PRAGMA query_only = ON")

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def schema_columns(self) -> tuple[str, ...]:
        with self._lock:
            rows = self._connection.execute("PRAGMA table_info(transactions)").fetchall()
        return tuple(str(row["name"]) for row in rows)

    def search(
        self,
        customer_id: str,
        criteria: TransactionSearchCriteria,
        *,
        excluded_transaction_ids: tuple[str, ...] = (),
        limit: int = MAX_RESULTS,
    ) -> TransactionSearchResult:
        """Retrieve a safe candidate set, rerank it, and return the best matches."""

        if not customer_id.strip():
            raise ValueError("customer_id is required")
        if not criteria.is_discriminative:
            raise InsufficientTransactionCriteriaError(
                "provide merchant, approximate amount, date, or location"
            )
        bounded_limit = min(max(int(limit), 1), MAX_RESULTS)
        sql, parameters = self._compile_query(
            customer_id,
            criteria,
            excluded_transaction_ids=excluded_transaction_ids,
            limit=bounded_limit,
        )
        started = time.monotonic()
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        retrieved = tuple(self._to_transaction(row) for row in rows)
        ranked = tuple(
            candidate
            for candidate in sorted(
                (_rank_transaction(transaction, criteria) for transaction in retrieved),
                key=lambda candidate: (
                    candidate.score,
                    candidate.transaction.transaction_date,
                ),
                reverse=True,
            )
            if candidate.score >= MIN_RELEVANCE_SCORE
        )[:bounded_limit]
        LOGGER.info(
            json.dumps(
                {
                    "event": "transaction.search.completed",
                    "latency_ms": latency_ms,
                    "retrieved_count": len(retrieved),
                    "result_count": len(ranked),
                    "top_score": ranked[0].score if ranked else None,
                    "limit": bounded_limit,
                    "has_merchant": criteria.merchant_query is not None,
                    "has_amount": criteria.approximate_amount is not None,
                    "has_date": criteria.date_from is not None or criteria.date_to is not None,
                    "has_location": criteria.country is not None or criteria.city is not None,
                    "excluded_count": len(excluded_transaction_ids),
                }
            )
        )
        return TransactionSearchResult(
            criteria=criteria,
            ranked_transactions=ranked,
            sql=sql,
            retrieved_count=len(retrieved),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _compile_query(
        customer_id: str,
        criteria: TransactionSearchCriteria,
        *,
        excluded_transaction_ids: tuple[str, ...],
        limit: int,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses = ["customer_id = ?"]
        parameters: list[Any] = [customer_id]

        if excluded_transaction_ids:
            placeholders = ", ".join("?" for _ in excluded_transaction_ids)
            clauses.append(f"transaction_id NOT IN ({placeholders})")
            parameters.extend(excluded_transaction_ids)

        sql = (
            f"SELECT {', '.join(TRANSACTION_COLUMNS)} FROM transactions "
            f"WHERE {' AND '.join(clauses)} ORDER BY transaction_date DESC LIMIT ?"
        )
        parameters.append(limit)
        return sql, tuple(parameters)

    def _create_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id TEXT PRIMARY KEY,
                transaction_date TEXT NOT NULL,
                process_date TEXT NOT NULL,
                product_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                transaction_category TEXT,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                amount_usd REAL,
                channel TEXT NOT NULL,
                branch_id TEXT,
                merchant_name TEXT,
                merchant_category TEXT,
                transaction_country TEXT NOT NULL,
                transaction_city TEXT,
                transaction_status TEXT NOT NULL,
                response_code TEXT,
                is_fraud INTEGER NOT NULL,
                fraud_score REAL,
                latitude REAL,
                longitude REAL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_transactions_customer_date "
            "ON transactions(customer_id, transaction_date DESC)"
        )

    def _seed(self, transactions: tuple[Transaction, ...]) -> None:
        placeholders = ", ".join("?" for _ in TRANSACTION_COLUMNS)
        rows = [
            tuple(_sqlite_value(getattr(transaction, column)) for column in TRANSACTION_COLUMNS)
            for transaction in transactions
        ]
        with self._connection:
            self._connection.executemany(
                f"INSERT OR IGNORE INTO transactions ({', '.join(TRANSACTION_COLUMNS)}) "
                f"VALUES ({placeholders})",
                rows,
            )

    @staticmethod
    def _to_transaction(row: sqlite3.Row) -> Transaction:
        values = dict(row)
        values["is_fraud"] = bool(values["is_fraud"])
        return Transaction.model_validate(values)


def demo_fruit_transactions(
    customer_id: str,
    location_seed: int = 19,
) -> tuple[Transaction, ...]:
    """Create ten deterministic transactions with pseudo-random varied locations."""

    locations = [
        ("Argentina", "Buenos Aires", -34.6037, -58.3816),
        ("Brazil", "São Paulo", -23.5505, -46.6333),
        ("Chile", "Santiago", -33.4489, -70.6693),
        ("Colombia", "Bogotá", 4.7110, -74.0721),
        ("Costa Rica", "San José", 9.9281, -84.0907),
        ("Mexico", "Mexico City", 19.4326, -99.1332),
        ("Peru", "Lima", -12.0464, -77.0428),
        ("Portugal", "Lisbon", 38.7223, -9.1393),
        ("Spain", "Madrid", 40.4168, -3.7038),
        ("United States", "Miami", 25.7617, -80.1918),
    ]
    selected_locations = random.Random(location_seed).sample(locations, k=len(locations))
    fruits = (
        ("lemon", "Lemon Drop Market", 12.49),
        ("strawberry", "Strawberry Fields Shop", 18.95),
        ("coconut", "Coconut Island Grocer", 27.80),
        ("passion-fruit", "Passion Fruit Pantry", 34.25),
        ("banana", "Banana Bunch Market", 41.60),
        ("apple", "Apple Orchard Store", 56.90),
        ("papaya", "Papaya Sunrise Market", 63.40),
        ("peach", "Peach Grove Grocer", 78.15),
        ("grapes", "Grapes and Vine Market", 92.75),
        ("mango", "Mango Gold Store", 125.30),
    )
    anchor = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)
    transactions: list[Transaction] = []
    for index, ((fruit, merchant, amount), location) in enumerate(
        zip(fruits, selected_locations, strict=True),
        start=1,
    ):
        country, city, latitude, longitude = location
        transaction_time = anchor + timedelta(days=index - 1, hours=index)
        transactions.append(
            Transaction(
                transaction_id=f"FRUIT-{index:02d}-{fruit.upper()}",
                transaction_date=transaction_time,
                process_date=transaction_time.date(),
                product_id=f"CARD-{customer_id}",
                customer_id=customer_id,
                transaction_type="Card Purchase",
                transaction_category="Fruit purchase",
                amount=amount,
                currency="USD",
                amount_usd=amount,
                channel="E-commerce" if index % 2 else "POS",
                branch_id=None,
                merchant_name=merchant,
                merchant_category="Fruit and produce",
                transaction_country=country,
                transaction_city=city,
                transaction_status="Approved",
                response_code="00",
                is_fraud=False,
                fraud_score=round(0.01 * index, 2),
                latitude=latitude,
                longitude=longitude,
            )
        )
    return tuple(transactions)


def _sqlite_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def _rank_transaction(
    transaction: Transaction,
    criteria: TransactionSearchCriteria,
) -> RankedTransaction:
    """Score one candidate using only caller-provided, explainable features."""

    weighted_scores: list[tuple[str, float, float]] = []

    if criteria.merchant_query:
        haystack = " ".join(
            value
            for value in (
                transaction.merchant_name,
                transaction.merchant_category,
                transaction.transaction_category,
            )
            if value
        )
        weighted_scores.append(
            ("merchant", 5.0, _text_similarity(criteria.merchant_query, haystack))
        )
    if criteria.approximate_amount is not None:
        tolerance = max(
            MIN_AMOUNT_TOLERANCE,
            abs(criteria.approximate_amount) * AMOUNT_TOLERANCE_RATE,
        )
        distance = abs(transaction.amount - criteria.approximate_amount)
        weighted_scores.append(("amount", 4.0, 1 / (1 + distance / tolerance)))
    if criteria.date_from or criteria.date_to:
        transaction_day = transaction.transaction_date.date()
        lower = criteria.date_from or criteria.date_to
        upper = criteria.date_to or criteria.date_from
        assert lower is not None and upper is not None
        if lower <= transaction_day <= upper:
            date_score = 1.0
        else:
            distance_days = min(
                abs((transaction_day - lower).days), abs((transaction_day - upper).days)
            )
            date_score = 1 / (1 + distance_days)
        weighted_scores.append(("date", 3.0, date_score))

    for field_name, expected, actual, weight in (
        ("country", criteria.country, transaction.transaction_country, 2.5),
        ("city", criteria.city, transaction.transaction_city, 2.5),
        ("currency", criteria.currency, transaction.currency, 1.0),
        ("channel", criteria.channel, transaction.channel, 1.0),
        ("transaction_type", criteria.transaction_type, transaction.transaction_type, 1.0),
    ):
        if expected:
            weighted_scores.append(
                (field_name, weight, float(_normalize_text(expected) == _normalize_text(actual)))
            )

    total_weight = sum(weight for _, weight, _ in weighted_scores)
    score = (
        sum(weight * field_score for _, weight, field_score in weighted_scores) / total_weight
        if total_weight
        else 0.0
    )
    matched_fields = tuple(name for name, _, field_score in weighted_scores if field_score >= 0.75)
    return RankedTransaction(
        transaction=transaction,
        score=round(score, 4),
        matched_fields=matched_fields,
    )


def _text_similarity(expected: str, actual: str) -> float:
    query = _normalize_text(expected)
    candidate = _normalize_text(actual)
    if not query or not candidate:
        return 0.0
    if query in candidate:
        return 1.0

    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    token_overlap = len(query_tokens & candidate_tokens) / len(query_tokens)
    sequence_similarity = SequenceMatcher(None, query, candidate).ratio()
    return max(token_overlap, sequence_similarity)


def _normalize_text(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_marks.casefold().split())


def _canonical_merchant_query(value: str) -> str:
    aliases = {
        "fruta": "fruit",
        "frutas": "fruit",
        "limao": "lemon",
        "limon": "lemon",
        "morango": "strawberry",
        "fresa": "strawberry",
        "coco": "coconut",
        "maracuja": "passion fruit",
        "maracuya": "passion fruit",
        "maca": "apple",
        "manzana": "apple",
        "mamao": "papaya",
        "pessego": "peach",
        "durazno": "peach",
        "melocoton": "peach",
        "uva": "grapes",
        "uvas": "grapes",
        "manga": "mango",
    }
    return aliases.get(_normalize_text(value), value)


def _canonical_location(value: str) -> str:
    aliases = {
        "brasil": "Brazil",
        "colombia": "Colombia",
        "estados unidos": "United States",
        "eua": "United States",
        "eeuu": "United States",
        "espanha": "Spain",
        "espana": "Spain",
        "mexico": "Mexico",
        "lisboa": "Lisbon",
        "cidade do mexico": "Mexico City",
        "ciudad de mexico": "Mexico City",
    }
    return aliases.get(_normalize_text(value), value)
