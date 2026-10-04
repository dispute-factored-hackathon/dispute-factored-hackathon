"""Read-only connection to the synthetic lakehouse on MotherDuck (its PostgreSQL endpoint).

Shared by `dispute-db-seed-lakehouse` and the agents' lakehouse reader. Errors never include the
token: callers receive `LakehouseUnavailableError` with only the host and database name.
"""

import re

import certifi
import psycopg
from psycopg.conninfo import make_conninfo

from webapp.backend.config import Settings

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LakehouseUnavailableError(RuntimeError):
    """The lakehouse is not configured or cannot be reached. Never contains credentials."""


def lakehouse_schema(settings: Settings) -> str:
    if not _IDENTIFIER.match(settings.motherduck_schema):
        raise LakehouseUnavailableError(
            "MOTHERDUCK_SCHEMA must be a plain identifier such as 'silver'."
        )
    return settings.motherduck_schema


def lakehouse_target(settings: Settings) -> str:
    return (
        f"{settings.motherduck_pg_host}:{settings.motherduck_pg_port}/"
        f"{settings.motherduck_database}"
    )


def connect_lakehouse(settings: Settings, *, connect_timeout: int = 20) -> psycopg.Connection:
    """Open an autocommit, client-side-binding connection (the endpoint is a proxy)."""

    if settings.motherduck_token is None:
        raise LakehouseUnavailableError("MOTHERDUCK_TOKEN is not set. See .env.example.")
    dsn = make_conninfo(
        host=settings.motherduck_pg_host,
        port=settings.motherduck_pg_port,
        user="postgres",
        password=settings.motherduck_token.get_secret_value(),
        dbname=settings.motherduck_database,
        sslmode="verify-full",
        # certifi ships the ISRG Root X1 used by the endpoint; "system" is unreliable on Windows.
        sslrootcert=certifi.where(),
        connect_timeout=connect_timeout,
    )
    try:
        return psycopg.connect(dsn, cursor_factory=psycopg.ClientCursor, autocommit=True)
    except psycopg.OperationalError as error:
        raise LakehouseUnavailableError(
            f"Cannot connect to MotherDuck at {lakehouse_target(settings)} "
            "(check MOTHERDUCK_TOKEN, MOTHERDUCK_PG_HOST, MOTHERDUCK_PG_PORT and your network)."
        ) from error
