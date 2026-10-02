"""Connection pool shared by the PostgreSQL repositories."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool, PoolTimeout


class DatabaseUnavailableError(RuntimeError):
    """The database cannot be reached or has not been migrated. Never contains credentials."""


def describe_target(url: str) -> str:
    """Return host:port/dbname for messages, without user or password."""

    try:
        parts = conninfo_to_dict(url)
    except psycopg.ProgrammingError:
        return "the configured database"
    return f"{parts.get('host', 'localhost')}:{parts.get('port', 5432)}/{parts.get('dbname', '')}"


class Database:
    """Thin wrapper over psycopg_pool. Every connection uses UTC and returns dict rows."""

    def __init__(self, url: str, *, max_size: int = 10) -> None:
        self._target = describe_target(url)
        self._pool = ConnectionPool(
            url,
            min_size=1,
            max_size=max_size,
            open=False,
            kwargs={"row_factory": dict_row, "options": "-c timezone=UTC"},
            name="factored-postgres",
        )

    def open(self, *, timeout: float = 10.0) -> None:
        try:
            self._pool.open(wait=True, timeout=timeout)
        except PoolTimeout as error:
            self._pool.close()
            raise DatabaseUnavailableError(
                f"Cannot connect to PostgreSQL at {self._target}. Start it with "
                "`docker compose up -d db`, then run `uv run dispute-db-migrate`."
            ) from error

    def close(self) -> None:
        self._pool.close()

    def check_migrated(self, expected_revision: str) -> None:
        """Fail fast unless the schema is at the revision this code was written for."""

        try:
            with self.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                row = cursor.fetchone()
        except psycopg.errors.UndefinedTable as error:
            raise DatabaseUnavailableError(
                f"PostgreSQL at {self._target} has no schema yet. Run `uv run dispute-db-migrate`."
            ) from error
        current = row["version_num"] if row else None
        if current != expected_revision:
            raise DatabaseUnavailableError(
                f"PostgreSQL at {self._target} is at revision {current!r}, expected "
                f"{expected_revision!r}. Run `uv run dispute-db-migrate`."
            )

    @contextmanager
    def cursor(self) -> Iterator[psycopg.Cursor[DictRow]]:
        """Yield a cursor in one transaction: commit on success, roll back on any error."""

        with self._pool.connection() as connection, connection.cursor() as cursor:
            yield cursor
