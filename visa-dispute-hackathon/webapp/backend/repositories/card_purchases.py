"""Card purchases read from both stores: the lakehouse (seeded history) and PostgreSQL (live).

The agents read a customer's card purchases from the synthetic lakehouse, where the seeded
customers' full history lives, and from PostgreSQL, where the web app writes new activity (shop
purchases, sign-ups) that the lakehouse does not have yet. Results are merged and deduplicated by
`transaction_id`; PostgreSQL wins because it is the authoritative, most recent copy.

Every query is scoped to one `customer_id`, only returns purchases on credit or debit cards, and
never reads more than the last four digits of a card number.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Lock
from typing import Any

import psycopg

from webapp.backend.config import Settings
from webapp.backend.db import lakehouse_mapping as mapping
from webapp.backend.db.motherduck import (
    LakehouseUnavailableError,
    connect_lakehouse,
    lakehouse_schema,
)
from webapp.backend.models.card_transaction import CardTransaction
from webapp.backend.repositories.interfaces import CardPurchaseRepository

LOGGER = logging.getLogger(__name__)

DEFAULT_LIMIT = 500
LAKEHOUSE_TIMEOUT_SECONDS = 6.0
LAKEHOUSE_CACHE_SECONDS = 300.0
_CARD_FIELDS = ("card_type", "card_last_four", "card_status")


def _log(event: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, default=str))


def card_transaction_from_lakehouse_row(row: dict[str, Any]) -> CardTransaction:
    """Map one joined `silver` row (labels in capitals) to the app's card purchase."""

    transaction_row = {key: value for key, value in row.items() if key not in _CARD_FIELDS}
    return CardTransaction(
        transaction=mapping.map_transaction(transaction_row),
        card_type=mapping.label(row["card_type"]) or "Credit Card",
        card_last_four=str(row["card_last_four"] or "")[-4:],
        card_status=mapping.label(row["card_status"]) or "Active",
        source="lakehouse",
    )


class LakehouseCardPurchaseReader:
    """Read-only access to one customer's card purchases in `lakehouse.<schema>`."""

    def __init__(
        self,
        settings: Settings,
        *,
        connect: Callable[[], psycopg.Connection] | None = None,
    ) -> None:
        self.schema = lakehouse_schema(settings)
        self._connect = connect or (lambda: connect_lakehouse(settings, connect_timeout=5))

    def _select(self, extra: str) -> str:
        s = self.schema
        columns = ", ".join(
            (
                "CAST(t.transaction_location AS VARCHAR) AS transaction_location"
                if column == "transaction_location"
                else f"t.{column}"
            )
            for column in mapping.TRANSACTION_COLUMNS
        )
        card_types = ", ".join(f"'{card_type}'" for card_type in mapping.CARD_TYPES)
        # The full card number never leaves the query: only its last four digits are selected.
        return (
            f"SELECT {columns}, p.product_type AS card_type, "
            "right(p.product_number, 4) AS card_last_four, p.product_status AS card_status "
            f"FROM {s}.transactions t "
            f"JOIN {s}.products p ON p.product_id = t.product_id "
            "AND p.customer_id = t.customer_id "
            "WHERE t.customer_id = %s AND t.transaction_type = 'PURCHASE' "
            f"AND p.product_type IN ({card_types}){extra}"
        )

    def _rows(self, query: str, params: tuple[Any, ...]) -> list[CardTransaction]:
        with self._connect() as connection:
            cursor = connection.execute(query, params)
            names = [column.name for column in cursor.description or []]
            rows = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
        purchases = []
        for row in rows:
            try:
                purchases.append(card_transaction_from_lakehouse_row(row))
            except (ValueError, KeyError, TypeError):
                _log("lakehouse.card_purchase.rejected_row")
        return purchases

    def list_by_customer(
        self, customer_id: str, *, limit: int = DEFAULT_LIMIT
    ) -> list[CardTransaction]:
        return self._rows(
            self._select(" ORDER BY t.transaction_date DESC, t.transaction_id DESC LIMIT %s"),
            (customer_id, max(limit, 0)),
        )

    def get_for_customer(self, customer_id: str, transaction_id: str) -> CardTransaction | None:
        rows = self._rows(self._select(" AND t.transaction_id = %s"), (customer_id, transaction_id))
        return rows[0] if rows else None


class CombinedCardPurchaseRepository:
    """Lakehouse + PostgreSQL card purchases, deduplicated; PostgreSQL alone if the lakehouse fails."""

    def __init__(
        self,
        postgres: CardPurchaseRepository,
        lakehouse: CardPurchaseRepository | None,
        *,
        timeout_seconds: float = LAKEHOUSE_TIMEOUT_SECONDS,
        cache_seconds: float = LAKEHOUSE_CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.postgres = postgres
        self.lakehouse = lakehouse
        self.timeout_seconds = timeout_seconds
        self.cache_seconds = cache_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, list[CardTransaction]]] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="lakehouse")

    @classmethod
    def from_settings(
        cls, postgres: CardPurchaseRepository, settings: Settings
    ) -> CombinedCardPurchaseRepository:
        lakehouse = None
        if settings.motherduck_token is not None:
            try:
                lakehouse = LakehouseCardPurchaseReader(settings)
            except LakehouseUnavailableError as error:
                _log("lakehouse.card_purchases.disabled", reason=str(error))
        else:
            _log("lakehouse.card_purchases.disabled", reason="MOTHERDUCK_TOKEN is not set")
        return cls(postgres, lakehouse)

    def _with_timeout(self, call: Callable[[], Any]) -> Any:
        future = self._executor.submit(call)
        try:
            return future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            raise LakehouseUnavailableError("the lakehouse did not answer in time") from None

    def _lakehouse_history(self, customer_id: str, limit: int) -> list[CardTransaction]:
        if self.lakehouse is None:
            return []
        now = self._clock()
        with self._lock:
            cached = self._cache.get(customer_id)
        if cached is not None and now - cached[0] < self.cache_seconds:
            return cached[1]
        lakehouse = self.lakehouse
        started = time.monotonic()
        try:
            history = self._with_timeout(
                lambda: lakehouse.list_by_customer(customer_id, limit=limit)
            )
        except (LakehouseUnavailableError, psycopg.Error) as error:
            _log(
                "lakehouse.card_purchases.unavailable",
                error_type=type(error).__name__,
                fallback="postgres_only",
            )
            return []
        _log(
            "lakehouse.card_purchases.loaded",
            count=len(history),
            latency_ms=round((time.monotonic() - started) * 1000, 2),
        )
        with self._lock:
            self._cache[customer_id] = (now, history)
        return history

    def list_by_customer(
        self, customer_id: str, *, limit: int = DEFAULT_LIMIT
    ) -> list[CardTransaction]:
        merged: dict[str, CardTransaction] = {
            item.transaction.transaction_id: item
            for item in self._lakehouse_history(customer_id, limit)
            if item.transaction.customer_id == customer_id
        }
        for item in self.postgres.list_by_customer(customer_id, limit=limit):
            merged[item.transaction.transaction_id] = item  # PostgreSQL is authoritative
        ordered = sorted(
            merged.values(),
            key=lambda item: (item.transaction.transaction_date, item.transaction.transaction_id),
            reverse=True,
        )
        return ordered[: max(limit, 0)]

    def get_for_customer(self, customer_id: str, transaction_id: str) -> CardTransaction | None:
        found = self.postgres.get_for_customer(customer_id, transaction_id)
        if found is not None or self.lakehouse is None:
            return found
        for item in self._lakehouse_history(customer_id, DEFAULT_LIMIT):
            if item.transaction.transaction_id == transaction_id:
                return item
        return None
