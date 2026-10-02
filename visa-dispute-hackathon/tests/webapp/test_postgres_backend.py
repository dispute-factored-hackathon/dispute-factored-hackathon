"""PostgreSQL-only guarantees: schema, least privilege, session hashing and failure modes."""

import secrets

import psycopg
import pytest
from alembic import command
from factories import (
    make_complaint,
    make_customer,
    make_product,
    make_session,
    make_transaction,
)
from psycopg import sql
from psycopg.conninfo import make_conninfo

from webapp.backend.config import Settings
from webapp.backend.db import migrate
from webapp.backend.db.database import Database, DatabaseUnavailableError
from webapp.backend.repositories.postgres import hash_session_id, normalize_search_name
from webapp.backend.repositories.registry import BackendConfigurationError, build_repositories


@pytest.fixture
def repos(clean_postgres):
    built = build_repositories(
        Settings(_env_file=None, repository_backend="postgres", database_url=clean_postgres.app_url)
    )
    yield built
    built.close()


def scalar(url: str, query: str, params: tuple = ()):
    with psycopg.connect(url) as connection:
        row = connection.execute(query, params).fetchone()
    return row[0] if row else None


# ----------------------------------------------------------------------------- sessions


def test_session_id_is_never_stored_in_plaintext(repos, clean_postgres):
    repos.customers.create(make_customer("C1"))
    session_id = "very-secret-session-cookie-value"
    repos.sessions.create(make_session(session_id))

    stored = scalar(clean_postgres.owner_url, "SELECT session_hash FROM sessions")
    dump = scalar(clean_postgres.owner_url, "SELECT row_to_json(s)::text FROM sessions s")

    assert stored == hash_session_id(session_id)
    assert len(stored) == 64
    assert session_id not in dump


def test_session_survives_a_new_connection_pool_like_an_app_restart(repos, clean_postgres):
    repos.customers.create(make_customer("C1"))
    session = make_session("persisted-session")
    repos.sessions.create(session)

    restarted = build_repositories(
        Settings(_env_file=None, repository_backend="postgres", database_url=clean_postgres.app_url)
    )
    try:
        assert restarted.sessions.get("persisted-session") == session
    finally:
        restarted.close()


def test_expired_sessions_are_purged_when_a_new_session_is_created(repos, clean_postgres):
    from datetime import UTC, datetime, timedelta

    repos.customers.create(make_customer("C1"))
    now = datetime.now(UTC)
    repos.sessions.create(
        make_session("old", created_at=now - timedelta(days=2), expires_at=now - timedelta(days=1))
    )

    repos.sessions.create(
        make_session("fresh", created_at=now, expires_at=now + timedelta(hours=1))
    )

    assert repos.sessions.get("old") is None
    assert repos.sessions.get("fresh") is not None


def test_deleting_a_customer_cascades_to_their_sessions(repos, clean_postgres):
    repos.customers.create(make_customer("C1"))
    repos.sessions.create(make_session("s1"))

    with psycopg.connect(clean_postgres.owner_url) as connection:
        connection.execute("DELETE FROM customers WHERE customer_id = 'C1'")

    assert repos.sessions.get("s1") is None


# ----------------------------------------------------------------------------- least privilege


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM customers",
        "DELETE FROM products",
        "DELETE FROM transactions",
        "DELETE FROM complaints",
        "TRUNCATE sessions",
        "DROP TABLE customers",
        "ALTER TABLE customers ADD COLUMN pwned text",
        "CREATE TABLE intruder (id int)",
        "UPDATE alembic_version SET version_num = 'x'",
        "INSERT INTO alembic_version VALUES ('x')",
    ],
)
def test_application_role_cannot_destroy_data_or_change_the_schema(clean_postgres, statement):
    with (
        psycopg.connect(clean_postgres.app_url) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(statement)


def test_application_role_can_do_what_the_app_needs(clean_postgres):
    with psycopg.connect(clean_postgres.app_url) as connection:
        connection.execute("SELECT version_num FROM alembic_version").fetchone()
        connection.execute("DELETE FROM sessions")
        connection.execute("SELECT count(*) FROM customers").fetchone()


def test_application_role_is_not_a_superuser_and_cannot_create_roles(clean_postgres):
    row = (
        psycopg.connect(clean_postgres.app_url)
        .execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = current_user"
        )
        .fetchone()
    )

    assert row == (False, False, False)


# ----------------------------------------------------------------------------- integrity


def test_foreign_keys_are_enforced(repos):
    with pytest.raises(ValueError, match=r"Customer does not exist."):
        repos.products.create(make_product("P1", "no-such-customer"))
    repos.customers.create(make_customer("C1"))
    with pytest.raises(ValueError, match=r"Customer or product does not exist."):
        repos.transactions.create(make_transaction("T1", "C1", "no-such-product"))
    with pytest.raises(ValueError, match=r"Customer does not exist."):
        repos.complaints.create(make_complaint("K1", "no-such-customer"))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repos.sessions.create(make_session("s", "no-such-customer"))


def test_duplicate_primary_keys_are_rejected_with_clear_errors(repos):
    repos.customers.create(make_customer("C1"))
    repos.products.create(make_product("P1", "C1"))
    repos.transactions.create(make_transaction("T1"))
    repos.complaints.create(make_complaint("K1"))

    with pytest.raises(ValueError, match=r"Customer already exists."):
        repos.customers.create(make_customer("C1", document_number="another"))
    with pytest.raises(ValueError, match=r"Product already exists."):
        repos.products.create(make_product("P1", "C1"))
    with pytest.raises(ValueError, match=r"Transaction already exists."):
        repos.transactions.create(make_transaction("T1"))
    with pytest.raises(ValueError, match=r"Complaint already exists."):
        repos.complaints.create(make_complaint("K1"))


def test_a_failed_write_leaves_no_partial_row(repos):
    repos.customers.create(make_customer("C1", mobile_phone="+1"))

    with pytest.raises(ValueError):
        repos.customers.create(make_customer("C2", mobile_phone="+1"))

    assert repos.customers.get_by_id("C2") is None


def test_search_normalisation_matches_the_mock_implementation():
    from webapp.backend.repositories.mock import MockCustomerRepository

    for text in ("José María  Pérez", "ÁÉÍÓÚ ñandú", "  MIXED   Case ", "", "Zoë Müller-Åberg"):
        assert normalize_search_name(text) == MockCustomerRepository._normalize_name(text)


def test_session_hash_is_a_stable_sha256_hex_digest():
    assert hash_session_id("abc") == hash_session_id("abc")
    assert hash_session_id("abc") != hash_session_id("abd")
    assert len(hash_session_id("abc")) == 64


# ----------------------------------------------------------------------------- migrations


def test_migrations_are_idempotent_and_reach_the_expected_revision(clean_postgres):
    migrate.upgrade(clean_postgres.owner_url, None, quiet=True)
    migrate.upgrade(clean_postgres.owner_url, None, quiet=True)

    version = scalar(clean_postgres.owner_url, "SELECT version_num FROM alembic_version")

    assert version == migrate.expected_revision()


def test_migration_can_be_downgraded_and_upgraded_again(postgres_database):
    name = f"factored_roundtrip_{secrets.token_hex(3)}"
    with psycopg.connect(postgres_database.server_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            url = make_conninfo(postgres_database.server_url, dbname=name)
            config = migrate.alembic_config(url, quiet=True)
            command.upgrade(config, "head")
            command.downgrade(config, "base")
            tables = scalar(
                url, "SELECT count(*) FROM pg_tables WHERE tablename IN ('customers','sessions')"
            )
            command.upgrade(config, "head")
            assert tables == 0
            assert scalar(url, "SELECT count(*) FROM customers") == 0
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


class _FakeCursor:
    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return None  # the role does not exist yet

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConnection:
    def transaction(self):
        return _FakeCursor()

    def cursor(self):
        return _FakeCursor()


def test_creating_the_app_role_requires_a_password():
    with pytest.raises(migrate.MigrationError, match=r"POSTGRES_APP_PASSWORD"):
        migrate.ensure_app_role(_FakeConnection(), database="factored", password=None)


# ----------------------------------------------------------------------------- failure modes


def test_unreachable_database_reports_a_helpful_error_without_credentials():
    database = Database("postgresql://factored_app:SuperSecretPw9@127.0.0.1:1/factored")

    with pytest.raises(DatabaseUnavailableError) as raised:
        database.open(timeout=1)

    message = str(raised.value)
    assert "SuperSecretPw9" not in message
    assert "factored_app" not in message
    assert "docker compose up -d db" in message
    assert "127.0.0.1:1/factored" in message


def test_unmigrated_database_is_rejected_with_the_migration_command(postgres_database):
    name = f"factored_empty_{secrets.token_hex(3)}"
    with psycopg.connect(postgres_database.server_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            database = Database(make_conninfo(postgres_database.server_url, dbname=name))
            database.open()
            try:
                with pytest.raises(DatabaseUnavailableError, match=r"dispute-db-migrate"):
                    database.check_migrated(migrate.expected_revision())
            finally:
                database.close()
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_outdated_schema_revision_is_rejected(clean_postgres):
    database = Database(clean_postgres.app_url)
    database.open()
    try:
        with pytest.raises(DatabaseUnavailableError, match=r"expected 'not-the-head'"):
            database.check_migrated("not-the-head")
    finally:
        database.close()


def test_postgres_backend_requires_a_database_url():
    settings = Settings(_env_file=None, repository_backend="postgres")

    with pytest.raises(BackendConfigurationError, match=r"DATABASE_URL"):
        build_repositories(settings)


def test_nul_bytes_are_rejected_as_invalid_input_not_as_a_server_error(repos):
    """Regression: PostgreSQL text cannot hold NUL, which used to surface as psycopg.DataError."""

    with pytest.raises(ValueError, match=r"NUL"):
        repos.customers.create(make_customer("C1", first_name="Ana\x00"))
    with pytest.raises(ValueError, match=r"NUL"):
        repos.complaints.create(make_complaint("K1", description="bad\x00text"))

    assert repos.customers.get_by_id("C1") is None
    assert repos.customers.search_by_full_name("ana\x00") == []
