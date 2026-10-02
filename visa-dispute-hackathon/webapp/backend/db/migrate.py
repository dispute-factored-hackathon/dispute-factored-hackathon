"""Run Alembic migrations and (re)create the least-privilege application role.

    uv run dispute-db-migrate

Uses DATABASE_URL_OWNER. It is idempotent: `alembic upgrade head` skips applied revisions and
the role grants are re-applied. New revisions are authored with plain Alembic:

    uv run alembic revision -m "describe the change"
"""

from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql

from webapp.backend.config import get_settings
from webapp.backend.db.database import describe_target

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
APP_ROLE = "factored_app"

# What the web application may do. It can never alter the schema, delete customers, products,
# transactions or complaints, or write the migration history.
APP_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE ON customers, products, transactions, complaints TO {role}",
    (
        "GRANT SELECT, INSERT, UPDATE ON service_agents, call_center_interactions, "
        "call_transcripts, satisfaction_surveys TO {role}"
    ),
    "GRANT SELECT, INSERT, DELETE ON sessions TO {role}",
    "GRANT SELECT ON alembic_version TO {role}",
)


class MigrationError(RuntimeError):
    pass


def alembic_config(owner_url: str | None = None, *, quiet: bool = False) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if owner_url:
        config.attributes["owner_url"] = owner_url
    config.attributes["configure_logging"] = not quiet
    return config


def expected_revision() -> str:
    """The newest revision shipped with this code; the app refuses to run on an older database."""

    head = ScriptDirectory.from_config(alembic_config(quiet=True)).get_current_head()
    if head is None:
        raise MigrationError("No Alembic revisions found.")
    return head


def ensure_app_role(connection: psycopg.Connection, *, database: str, password: str | None) -> None:
    """Create or refresh the application role and grant only the privileges it needs."""

    role = sql.Identifier(APP_ROLE)
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
        exists = cursor.fetchone() is not None
        if not exists:
            if not password:
                raise MigrationError(
                    f"Role {APP_ROLE} does not exist. Set POSTGRES_APP_PASSWORD so it can be created."
                )
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(role, sql.Literal(password))
            )
        elif password:
            cursor.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(role, sql.Literal(password)))
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), role)
        )
        cursor.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        for statement in APP_GRANTS:
            cursor.execute(sql.SQL(statement).format(role=role))


def upgrade(owner_url: str, app_password: str | None, *, quiet: bool = False) -> None:
    command.upgrade(alembic_config(owner_url, quiet=quiet), "head")
    with psycopg.connect(owner_url) as connection:
        ensure_app_role(connection, database=connection.info.dbname, password=app_password)


def main() -> int:
    settings = get_settings()
    if settings.database_url_owner is None:
        print("DATABASE_URL_OWNER is not set. Add it to .env (see .env.example).")
        return 2
    owner_url = settings.database_url_owner.get_secret_value()
    password = (
        settings.postgres_app_password.get_secret_value()
        if settings.postgres_app_password
        else None
    )
    try:
        upgrade(owner_url, password)
    except MigrationError as error:
        print(f"Migration failed: {error}")
        return 1
    except Exception as error:
        # Never echo the exception text: driver messages can include connection details.
        print(
            f"Migration failed for {describe_target(owner_url)} ({type(error).__name__}). "
            "Is the database running (`docker compose up -d db`) and DATABASE_URL_OWNER correct?"
        )
        return 1
    print(f"Database is at revision {expected_revision()}; role '{APP_ROLE}' is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
