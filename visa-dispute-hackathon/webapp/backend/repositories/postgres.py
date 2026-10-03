"""PostgreSQL implementations of the repository contracts in `interfaces.py`.

This is the web app's only data store. Every statement is parameterised (identifiers come from
fixed model field names), so customer input can never change a query.
"""

import hashlib
import unicodedata
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from psycopg import errors, sql
from pydantic import BaseModel

from webapp.backend.config import Settings
from webapp.backend.db.database import Database
from webapp.backend.db.migrate import expected_revision
from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.models.session import CustomerSession
from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.interfaces import Repositories

ModelT = TypeVar("ModelT", bound=BaseModel)


class BackendConfigurationError(RuntimeError):
    """The database settings are incomplete. Messages never include credentials."""


def normalize_search_name(value: str) -> str:
    """Case- and accent-insensitive form used for name search."""

    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_marks.split())


def hash_session_id(session_id: str) -> str:
    """Sessions are stored by SHA-256 so a leaked table cannot be replayed as cookies."""

    return hashlib.sha256(session_id.encode()).hexdigest()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def dump_model(model: BaseModel) -> dict[str, Any]:
    values = {
        name: value.value if isinstance(value, Enum) else value
        for name, value in model.model_dump().items()
    }
    # PostgreSQL text cannot hold NUL; refuse it as ordinary invalid input rather than a 500.
    if any(isinstance(value, str) and "\x00" in value for value in values.values()):
        raise ValueError("Text fields cannot contain NUL characters.")
    return values


class _Table(Generic[ModelT]):
    """Shared plumbing for one table whose columns match the model's field names."""

    table: str
    model: type[ModelT]
    key: str

    def __init__(self, database: Database) -> None:
        self.database = database
        self.columns = tuple(self.model.model_fields)

    def _select(self, where: sql.Composable | None = None, tail: str = "") -> sql.Composed:
        query = sql.SQL("SELECT {columns} FROM {table}").format(
            columns=sql.SQL(", ").join(map(sql.Identifier, self.columns)),
            table=sql.Identifier(self.table),
        )
        if where is not None:
            query += sql.SQL(" WHERE ") + where
        return query + sql.SQL(tail)

    def _insert(self, values: dict[str, Any]) -> sql.Composed:
        return sql.SQL("INSERT INTO {table} ({columns}) VALUES ({values})").format(
            table=sql.Identifier(self.table),
            columns=sql.SQL(", ").join(map(sql.Identifier, values)),
            values=sql.SQL(", ").join(map(sql.Placeholder, values)),
        )

    def _update(self, values: dict[str, Any]) -> sql.Composed:
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(name), sql.Placeholder(name))
            for name in values
            if name != self.key
        )
        return sql.SQL("UPDATE {table} SET {assignments} WHERE {key} = {key_value}").format(
            table=sql.Identifier(self.table),
            assignments=assignments,
            key=sql.Identifier(self.key),
            key_value=sql.Placeholder(self.key),
        )

    def _fetch_one(self, where: sql.Composable, params: tuple[Any, ...]) -> ModelT | None:
        with self.database.cursor() as cursor:
            cursor.execute(self._select(where), params)
            row = cursor.fetchone()
        return self.model.model_validate(row) if row else None

    def _fetch_many(
        self, where: sql.Composable | None, params: tuple[Any, ...], tail: str
    ) -> list[ModelT]:
        with self.database.cursor() as cursor:
            cursor.execute(self._select(where, tail), params)
            return [self.model.model_validate(row) for row in cursor.fetchall()]

    def _where(self, column: str) -> sql.Composed:
        return sql.SQL("{} = %s").format(sql.Identifier(column))


class PostgresCustomerRepository(_Table[Customer]):
    table = "customers"
    model = Customer
    key = "customer_id"

    @staticmethod
    def _values(customer: Customer) -> dict[str, Any]:
        values = dump_model(customer)
        values["search_name"] = normalize_search_name(f"{customer.first_name} {customer.last_name}")
        return values

    @staticmethod
    def _unique_error(error: errors.UniqueViolation) -> ValueError:
        constraint = error.diag.constraint_name
        if constraint == "customers_document_number_key":
            return ValueError("FACTORED_ID already exists.")
        if constraint == "customers_mobile_phone_key":
            return ValueError("Phone number already exists.")
        return ValueError("Customer already exists.")

    def create(self, customer: Customer) -> Customer:
        values = self._values(customer)
        try:
            with self.database.cursor() as cursor:
                cursor.execute(self._insert(values), values)
        except errors.UniqueViolation as error:
            raise self._unique_error(error) from error
        return customer

    def get_by_id(self, customer_id: str) -> Customer | None:
        return self._fetch_one(self._where("customer_id"), (customer_id,))

    def get_by_document(self, document_number: str) -> Customer | None:
        return self._fetch_one(self._where("document_number"), (document_number,))

    def get_by_phone(self, mobile_phone: str) -> Customer | None:
        return self._fetch_one(self._where("mobile_phone"), (mobile_phone,))

    def search_by_full_name(self, query: str, *, limit: int = 10) -> list[Customer]:
        if "\x00" in query:
            return []  # no stored name can contain NUL, and PostgreSQL rejects it as a parameter
        normalized = normalize_search_name(query)
        where = None
        params: tuple[Any, ...] = ()
        if normalized:
            where = sql.SQL("search_name LIKE %s ESCAPE '\\'")
            params = (f"%{_escape_like(normalized)}%",)
        return self._fetch_many(
            where, (*params, max(limit, 0)), " ORDER BY search_name, customer_id LIMIT %s"
        )

    def update(self, customer: Customer) -> Customer:
        values = self._values(customer)
        try:
            with self.database.cursor() as cursor:
                cursor.execute(self._update(values), values)
                if cursor.rowcount == 0:
                    raise ValueError("Customer does not exist.")
        except errors.UniqueViolation as error:
            raise self._unique_error(error) from error
        return customer


class PostgresProductRepository(_Table[Product]):
    table = "products"
    model = Product
    key = "product_id"

    def create(self, product: Product) -> Product:
        values = dump_model(product)
        try:
            with self.database.cursor() as cursor:
                cursor.execute(self._insert(values), values)
        except errors.UniqueViolation as error:
            raise ValueError("Product already exists.") from error
        except errors.ForeignKeyViolation as error:
            raise ValueError("Customer does not exist.") from error
        return product

    def get_by_id(self, product_id: str) -> Product | None:
        return self._fetch_one(self._where("product_id"), (product_id,))

    def list_by_customer(self, customer_id: str) -> list[Product]:
        return self._fetch_many(
            self._where("customer_id"), (customer_id,), " ORDER BY opening_date, product_id"
        )

    def update(self, product: Product) -> Product:
        values = dump_model(product)
        with self.database.cursor() as cursor:
            cursor.execute(self._update(values), values)
            if cursor.rowcount == 0:
                raise ValueError("Product does not exist.")
        return product


class PostgresTransactionRepository(_Table[Transaction]):
    table = "transactions"
    model = Transaction
    key = "transaction_id"

    def create(self, transaction: Transaction) -> Transaction:
        values = dump_model(transaction)
        try:
            with self.database.cursor() as cursor:
                cursor.execute(self._insert(values), values)
        except errors.UniqueViolation as error:
            raise ValueError("Transaction already exists.") from error
        except errors.ForeignKeyViolation as error:
            raise ValueError("Customer or product does not exist.") from error
        return transaction

    def get_by_id(self, transaction_id: str) -> Transaction | None:
        return self._fetch_one(self._where("transaction_id"), (transaction_id,))

    def list_by_customer(self, customer_id: str) -> list[Transaction]:
        return self._fetch_many(
            self._where("customer_id"),
            (customer_id,),
            " ORDER BY transaction_date DESC, transaction_id DESC",
        )

    def update(self, transaction: Transaction) -> Transaction:
        values = dump_model(transaction)
        with self.database.cursor() as cursor:
            cursor.execute(self._update(values), values)
            if cursor.rowcount == 0:
                raise ValueError("Transaction does not exist.")
        return transaction


class PostgresComplaintRepository(_Table[Complaint]):
    table = "complaints"
    model = Complaint
    key = "complaint_id"

    def create(self, complaint: Complaint) -> Complaint:
        values = dump_model(complaint)
        try:
            with self.database.cursor() as cursor:
                cursor.execute(self._insert(values), values)
        except errors.UniqueViolation as error:
            raise ValueError("Complaint already exists.") from error
        except errors.ForeignKeyViolation as error:
            raise ValueError("Customer does not exist.") from error
        return complaint

    def get_by_id(self, complaint_id: str) -> Complaint | None:
        return self._fetch_one(self._where("complaint_id"), (complaint_id,))

    def list_by_customer(self, customer_id: str) -> list[Complaint]:
        return self._fetch_many(
            self._where("customer_id"),
            (customer_id,),
            " ORDER BY creation_date DESC, complaint_id DESC",
        )

    def update(self, complaint: Complaint) -> Complaint:
        values = dump_model(complaint)
        with self.database.cursor() as cursor:
            cursor.execute(self._update(values), values)
            if cursor.rowcount == 0:
                raise ValueError("Complaint does not exist.")
        return complaint


class PostgresSessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, session: CustomerSession) -> CustomerSession:
        with self.database.cursor() as cursor:
            # Opportunistic cleanup keeps the table small without a background job.
            cursor.execute("DELETE FROM sessions WHERE expires_at <= %s", (datetime.now(UTC),))
            cursor.execute(
                "INSERT INTO sessions "
                "(session_hash, customer_id, authentication_method, created_at, expires_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    hash_session_id(session.session_id),
                    session.customer_id,
                    session.authentication_method.value,
                    session.created_at,
                    session.expires_at,
                ),
            )
        return session

    def get(self, session_id: str) -> CustomerSession | None:
        with self.database.cursor() as cursor:
            cursor.execute(
                "SELECT customer_id, authentication_method, created_at, expires_at "
                "FROM sessions WHERE session_hash = %s",
                (hash_session_id(session_id),),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return CustomerSession(session_id=session_id, **row)

    def delete(self, session_id: str) -> None:
        with self.database.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sessions WHERE session_hash = %s", (hash_session_id(session_id),)
            )


def open_repositories(settings: Settings) -> Repositories:
    """Open the connection pool, verify the schema revision and build every repository."""

    if settings.database_url is None:
        raise BackendConfigurationError(
            "DATABASE_URL (the factored_app role) is not set. See .env.example."
        )
    database = Database(
        settings.database_url.get_secret_value(), max_size=settings.database_pool_max_size
    )
    database.open()
    try:
        database.check_migrated(expected_revision())
    except Exception:
        database.close()
        raise
    return Repositories(
        customers=PostgresCustomerRepository(database),
        products=PostgresProductRepository(database),
        transactions=PostgresTransactionRepository(database),
        complaints=PostgresComplaintRepository(database),
        sessions=PostgresSessionRepository(database),
        close=database.close,
    )
