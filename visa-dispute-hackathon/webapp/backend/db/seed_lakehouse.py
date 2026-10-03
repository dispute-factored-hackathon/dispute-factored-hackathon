"""Seed the Docker PostgreSQL with cards, transactions and complaints from the lakehouse.

    uv run dispute-db-seed-lakehouse                 # 100 customers (roughly 2,000 transactions)
    uv run dispute-db-seed-lakehouse --customers 50
    uv run dispute-db-seed-lakehouse --dry-run       # read + validate only, writes nothing
    uv run dispute-db-seed-lakehouse --all           # every customer (long: ~1.4M transactions)

This is the web app's only source of customer data. The source is the synthetic hackathon dataset (`lakehouse.silver` on MotherDuck, read through its
PostgreSQL endpoint with `MOTHERDUCK_TOKEN`). The script only ever runs SELECTs there. It writes
with the owner role (`DATABASE_URL_OWNER`), is idempotent (existing rows are kept) and refuses
non-local targets unless `--allow-remote` is given.

Privacy: only the columns in `lakehouse_mapping.*_COLUMNS` are requested (no emails, addresses,
income or credit score), and card numbers are masked inside the SQL so the full number never
reaches this process.
"""

import argparse
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, TypeVar

import certifi
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import BaseModel, ValidationError

from webapp.backend.config import Settings, get_settings
from webapp.backend.db import lakehouse_mapping as mapping
from webapp.backend.db.database import describe_target
from webapp.backend.repositories.postgres import PostgresCustomerRepository, dump_model

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

DEFAULT_CUSTOMERS = 100
# Below this the demo has too little card activity to search and dispute; the report warns.
MIN_DEMO_TRANSACTIONS = 1_000
DEFAULT_CHUNK_SIZE = 200
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CARD_TYPES_SQL = ", ".join(f"'{card_type}'" for card_type in mapping.CARD_TYPES)


class SeedError(RuntimeError):
    """A user-fixable problem. Messages never contain credentials."""


class LakehouseSource(Protocol):
    def select_customer_ids(self, limit: int | None) -> list[str]: ...

    def fetch(self, entity: str, customer_ids: Sequence[str]) -> list[dict[str, Any]]: ...


@dataclass
class SeedReport:
    customers_selected: int = 0
    customers_inserted: int = 0
    customers_already_present: int = 0
    phones_cleared: int = 0
    cards_inserted: int = 0
    transactions_inserted: int = 0
    transactions_skipped: int = 0
    complaints_inserted: int = 0
    rows_rejected: int = 0
    # Transactions available to the demo afterwards (whole table, or the validated rows on a dry run).
    transactions_available: int = 0

    def lines(self) -> list[str]:
        present = f"(already present: {self.customers_already_present})"
        skipped = f"(skipped: {self.transactions_skipped})"
        warnings = []
        if self.transactions_available < MIN_DEMO_TRANSACTIONS:
            warnings.append(
                f"WARNING: only {self.transactions_available} transactions are available; the "
                f"demo needs at least {MIN_DEMO_TRANSACTIONS}. Re-run with a larger --customers."
            )
        return [
            f"customers selected      : {self.customers_selected}",
            f"customers inserted      : {self.customers_inserted} {present}",
            f"duplicate phones cleared: {self.phones_cleared}",
            f"cards inserted          : {self.cards_inserted}",
            f"transactions inserted   : {self.transactions_inserted} {skipped}",
            f"complaints inserted     : {self.complaints_inserted}",
            f"rows rejected by models : {self.rows_rejected}",
            f"transactions available  : {self.transactions_available}",
            *warnings,
        ]


# ----------------------------------------------------------------------------- MotherDuck


class MotherDuckSource:
    """Read-only access to `lakehouse.silver` through MotherDuck's PostgreSQL endpoint."""

    def __init__(self, settings: Settings) -> None:
        if settings.motherduck_token is None:
            raise SeedError("MOTHERDUCK_TOKEN is not set. Add it to .env (see .env.example).")
        if not _IDENTIFIER.match(settings.motherduck_schema):
            raise SeedError("MOTHERDUCK_SCHEMA must be a plain identifier such as 'silver'.")
        self.schema = settings.motherduck_schema
        self._target = f"{settings.motherduck_pg_host}/{settings.motherduck_database}"
        dsn = make_conninfo(
            host=settings.motherduck_pg_host,
            port=5432,
            user="postgres",
            password=settings.motherduck_token.get_secret_value(),
            dbname=settings.motherduck_database,
            sslmode="verify-full",
            # certifi ships the ISRG Root X1 used by the endpoint; "system" is unreliable on Windows.
            sslrootcert=certifi.where(),
            connect_timeout=20,
        )
        try:
            # Client-side binding: the endpoint is a proxy, so plain SQL text is the safest protocol.
            self._connection = psycopg.connect(
                dsn, cursor_factory=psycopg.ClientCursor, autocommit=True
            )
        except psycopg.OperationalError as error:
            raise SeedError(
                f"Cannot connect to MotherDuck at {self._target} "
                "(check MOTHERDUCK_TOKEN, MOTHERDUCK_PG_HOST and your network)."
            ) from error

    def close(self) -> None:
        self._connection.close()

    def _rows(
        self, query: sql.Composable | str, params: Sequence[Any] = ()
    ) -> list[dict[str, Any]]:
        cursor = self._connection.execute(query, params)
        names = [column.name for column in cursor.description or []]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def select_customer_ids(self, limit: int | None) -> list[str]:
        s = self.schema
        if limit is None:
            rows = self._rows(f"SELECT customer_id FROM {s}.customers ORDER BY customer_id")
        else:
            # Active customers that can really use the demo: an active credit card (for /shop)
            # and at least one transaction. hash() gives a deterministic, well-mixed sample.
            rows = self._rows(
                f"SELECT c.customer_id FROM {s}.customers c "
                "WHERE c.customer_status = 'ACTIVE' "
                f"AND EXISTS (SELECT 1 FROM {s}.products p WHERE p.customer_id = c.customer_id "
                "AND p.product_type = 'CREDIT CARD' AND p.product_status = 'ACTIVE') "
                f"AND EXISTS (SELECT 1 FROM {s}.transactions t WHERE t.customer_id = c.customer_id) "
                "ORDER BY hash(c.customer_id), c.customer_id LIMIT %s",
                (limit,),
            )
        return [row["customer_id"] for row in rows]

    def fetch(self, entity: str, customer_ids: Sequence[str]) -> list[dict[str, Any]]:
        if not customer_ids:
            return []
        s = self.schema
        marks = ", ".join(["%s"] * len(customer_ids))
        params = tuple(customer_ids)
        if entity == "customers":
            columns = ", ".join(mapping.CUSTOMER_COLUMNS)
            return self._rows(
                f"SELECT {columns} FROM {s}.customers WHERE customer_id IN ({marks})", params
            )
        if entity == "cards":
            columns = ", ".join(
                (
                    "repeat('*', greatest(length(product_number) - 4, 0)) "
                    "|| right(product_number, 4) AS product_number"
                    if column == "product_number"
                    else column
                )
                for column in mapping.PRODUCT_COLUMNS
            )
            return self._rows(
                f"SELECT {columns} FROM {s}.products WHERE customer_id IN ({marks}) "
                f"AND product_type IN ({_CARD_TYPES_SQL}) ORDER BY product_id",
                params,
            )
        if entity == "transactions":
            columns = ", ".join(
                (
                    "CAST(transaction_location AS VARCHAR) AS transaction_location"
                    if column == "transaction_location"
                    else column
                )
                for column in mapping.TRANSACTION_COLUMNS
            )
            return self._rows(
                f"SELECT {columns} FROM {s}.transactions WHERE customer_id IN ({marks}) "
                f"AND product_id IN (SELECT product_id FROM {s}.products "
                f"WHERE product_type IN ({_CARD_TYPES_SQL})) ORDER BY transaction_id",
                params,
            )
        if entity == "complaints":
            columns = ", ".join(mapping.COMPLAINT_COLUMNS)
            return self._rows(
                f"SELECT {columns} FROM {s}.complaints WHERE customer_id IN ({marks}) "
                "ORDER BY complaint_id",
                params,
            )
        raise ValueError(f"Unknown entity: {entity}")


# ----------------------------------------------------------------------------- loading


def chunked(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _insert_ignoring_conflicts(table: str, columns: Sequence[str]) -> sql.Composed:
    return sql.SQL(
        "INSERT INTO {table} ({columns}) VALUES ({values}) ON CONFLICT DO NOTHING"
    ).format(
        table=sql.Identifier(table),
        columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
        values=sql.SQL(", ").join(map(sql.Placeholder, columns)),
    )


def _validated(
    rows: Sequence[dict[str, Any]], build: Callable[[dict[str, Any]], M], report: SeedReport
) -> list[M]:
    models: list[M] = []
    for row in rows:
        try:
            models.append(build(row))
        except (ValidationError, KeyError, TypeError, ValueError):
            report.rows_rejected += 1  # one malformed source row must not abort the whole seed
    return models


def _insert_many(cursor: psycopg.Cursor, table: str, values: Sequence[dict[str, Any]]) -> int:
    if not values:
        return 0
    cursor.executemany(_insert_ignoring_conflicts(table, list(values[0])), values)
    return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0


def _clear_taken_phones(
    cursor: psycopg.Cursor, customers: list[Any], report: SeedReport
) -> list[Any]:
    """Phones are unique in the schema; keep the first owner and clear later duplicates."""

    phones = [customer.mobile_phone for customer in customers if customer.mobile_phone]
    owners: dict[str, str] = {}
    if phones:
        cursor.execute(
            "SELECT mobile_phone, customer_id FROM customers WHERE mobile_phone = ANY(%s)",
            (phones,),
        )
        owners = {row[0]: row[1] for row in cursor.fetchall()}
    seen: set[str] = set()
    cleaned = []
    for customer in customers:
        phone = customer.mobile_phone
        if phone and (
            owners.get(phone, customer.customer_id) != customer.customer_id or phone in seen
        ):
            customer = customer.model_copy(update={"mobile_phone": None})
            report.phones_cleared += 1
        elif phone:
            seen.add(phone)
        cleaned.append(customer)
    return cleaned


def _existing(cursor: psycopg.Cursor, table: str, column: str, ids: Sequence[str]) -> set[str]:
    if not ids:
        return set()
    cursor.execute(
        sql.SQL("SELECT {column} FROM {table} WHERE {column} = ANY(%s)").format(
            column=sql.Identifier(column), table=sql.Identifier(table)
        ),
        (list(ids),),
    )
    return {row[0] for row in cursor.fetchall()}


def seed(
    source: LakehouseSource,
    connection: psycopg.Connection | None,
    *,
    limit: int | None = DEFAULT_CUSTOMERS,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    keep_fraud_labels: bool = True,
    loaded_at: datetime | None = None,
    progress: Callable[[str], None] = lambda message: None,
) -> SeedReport:
    """Copy a customer sample (or everything when limit is None). connection=None is a dry run."""

    loaded_at = loaded_at or datetime.now(UTC)
    report = SeedReport()
    customer_ids = source.select_customer_ids(limit)
    report.customers_selected = len(customer_ids)
    total_chunks = max(1, -(-len(customer_ids) // chunk_size))

    for index, ids in enumerate(chunked(customer_ids, chunk_size), start=1):
        customers = _validated(
            source.fetch("customers", ids),
            lambda row: mapping.map_customer(row, loaded_at=loaded_at),
            report,
        )
        cards = _validated(
            source.fetch("cards", ids),
            lambda row: mapping.map_product(row, loaded_at=loaded_at),
            report,
        )
        transactions = _validated(
            source.fetch("transactions", ids),
            lambda row: mapping.map_transaction(row, keep_fraud_labels=keep_fraud_labels),
            report,
        )
        complaints = _validated(source.fetch("complaints", ids), mapping.map_complaint, report)

        if connection is None:  # dry run: everything above already validated the real rows
            report.customers_inserted += len(customers)
            report.cards_inserted += len(cards)
            report.transactions_inserted += len(transactions)
            report.complaints_inserted += len(complaints)
        else:
            with connection.transaction(), connection.cursor() as cursor:
                customers = _clear_taken_phones(cursor, customers, report)
                inserted = _insert_many(
                    cursor,
                    "customers",
                    [PostgresCustomerRepository._values(customer) for customer in customers],
                )
                report.customers_inserted += inserted
                report.customers_already_present += len(customers) - inserted

                present = _existing(cursor, "customers", "customer_id", ids)
                cards = [card for card in cards if card.customer_id in present]
                report.cards_inserted += _insert_many(
                    cursor, "products", [dump_model(card) for card in cards]
                )

                known_cards = _existing(
                    cursor, "products", "product_id", sorted({t.product_id for t in transactions})
                )
                usable = [t for t in transactions if t.product_id in known_cards]
                report.transactions_skipped += len(transactions) - len(usable)
                report.transactions_inserted += _insert_many(
                    cursor, "transactions", [dump_model(t) for t in usable]
                )

                complaints = [c for c in complaints if c.customer_id in present]
                report.complaints_inserted += _insert_many(
                    cursor, "complaints", [dump_model(c) for c in complaints]
                )
        progress(
            f"chunk {index}/{total_chunks}: customers={len(customers)} cards={len(cards)} "
            f"transactions={len(transactions)} complaints={len(complaints)}"
        )
    if connection is None:
        report.transactions_available = report.transactions_inserted
    else:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM transactions")
            report.transactions_available = cursor.fetchone()[0]
    return report


# ----------------------------------------------------------------------------- command line


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dispute-db-seed-lakehouse",
        description="Seed the local PostgreSQL with synthetic lakehouse data (read-only source).",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--customers", type=int, default=DEFAULT_CUSTOMERS, metavar="N")
    scope.add_argument("--all", action="store_true", help="load every customer (slow)")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--dry-run", action="store_true", help="read and validate, write nothing")
    parser.add_argument(
        "--hide-fraud-labels",
        action="store_true",
        help="load is_fraud=false and no fraud_score instead of the dataset labels",
    )
    parser.add_argument("--allow-remote", action="store_true", help="allow a non-local database")
    args = parser.parse_args(argv)
    if args.customers < 1 or args.chunk_size < 1:
        parser.error("--customers and --chunk-size must be positive")
    return args


def _check_target(owner_url: str, *, allow_remote: bool) -> None:
    host = conninfo_to_dict(owner_url).get("host", "") or ""
    if host not in LOCAL_HOSTS and not allow_remote:
        raise SeedError(
            f"Refusing to write to non-local host {host!r}. Use --allow-remote if you mean it."
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    try:
        connection = None
        if not args.dry_run:
            if settings.database_url_owner is None:
                raise SeedError("DATABASE_URL_OWNER is not set. Add it to .env (see .env.example).")
            owner_url = settings.database_url_owner.get_secret_value()
            _check_target(owner_url, allow_remote=args.allow_remote)
            try:
                connection = psycopg.connect(owner_url)
            except psycopg.OperationalError as error:
                raise SeedError(
                    f"Cannot connect to PostgreSQL at {describe_target(owner_url)}. Start it with "
                    "`docker compose up -d db` and run `uv run dispute-db-migrate` first."
                ) from error
        source = MotherDuckSource(settings)
    except SeedError as error:
        print(f"Seed failed: {error}")
        return 1

    mode = "DRY RUN (nothing is written)" if args.dry_run else "writing to PostgreSQL"
    scope = "all customers" if args.all else f"{args.customers} customers"
    print(
        f"Seeding {scope} from {settings.motherduck_database}.{settings.motherduck_schema}: {mode}"
    )
    try:
        report = seed(
            source,
            connection,
            limit=None if args.all else args.customers,
            chunk_size=args.chunk_size,
            keep_fraud_labels=not args.hide_fraud_labels,
            progress=print,
        )
    except psycopg.errors.UndefinedTable:
        print("Seed failed: the schema is missing. Run `uv run dispute-db-migrate` first.")
        return 1
    except psycopg.Error as error:
        # Driver messages can embed connection details, so only the class name is printed.
        print(f"Seed failed ({type(error).__name__}). Re-run; it is safe because it is idempotent.")
        return 1
    finally:
        source.close()
        if connection is not None:
            connection.close()

    print("\n".join(["", *report.lines()]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
