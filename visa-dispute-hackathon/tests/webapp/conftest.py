import os
import secrets
from collections.abc import Iterator
from dataclasses import dataclass

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

# The webapp tests exercise the in-memory backend through the module-level repositories. A
# developer's .env may select PostgreSQL, so pin the backend before `webapp` is imported.
os.environ["REPOSITORY_BACKEND"] = "mock"

from webapp.backend.db import migrate


@dataclass(frozen=True)
class PostgresTestDatabase:
    name: str
    owner_url: str
    app_url: str
    server_url: str


def _server_url() -> str:
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL is not set (see README: Run with PostgreSQL in Docker)")
    return url


@pytest.fixture(scope="session")
def postgres_database() -> Iterator[PostgresTestDatabase]:
    """A throwaway migrated database on the server named by TEST_POSTGRES_URL."""

    server_url = _server_url()
    try:
        admin = psycopg.connect(server_url, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("TEST_POSTGRES_URL is set but the server is not reachable")
    name = f"factored_test_{secrets.token_hex(4)}"
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    owner_url = make_conninfo(server_url, dbname=name)
    app_password = secrets.token_hex(8)
    try:
        migrate.upgrade(owner_url, app_password, quiet=True)
        app_url = make_conninfo(
            server_url, dbname=name, user=migrate.APP_ROLE, password=app_password
        )
        yield PostgresTestDatabase(name, owner_url, app_url, server_url)
    finally:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
        admin.close()


@pytest.fixture
def clean_postgres(postgres_database: PostgresTestDatabase) -> PostgresTestDatabase:
    with psycopg.connect(postgres_database.owner_url, autocommit=True) as connection:
        connection.execute(
            "TRUNCATE sessions, complaints, transactions, products, customers CASCADE"
        )
    return postgres_database
