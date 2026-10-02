"""Alembic environment: runs migrations with the owner role, never with the app role."""

from logging.config import fileConfig

import psycopg
from alembic import context
from sqlalchemy import create_engine, pool

from webapp.backend.config import get_settings

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def owner_url() -> str:
    # Tests and the dispute-db-migrate command pass the URL in-process so it is never written
    # to alembic.ini (where "%" in a password would also need escaping).
    explicit = config.attributes.get("owner_url")
    if explicit:
        return explicit
    configured = get_settings().database_url_owner
    if configured is None:
        raise RuntimeError("DATABASE_URL_OWNER is not set. Add it to .env (see .env.example).")
    return configured.get_secret_value()


def run_migrations_online() -> None:
    url = owner_url()
    # psycopg opens the connection itself, so both postgresql:// URLs and key=value DSNs work
    # and the password never goes through SQLAlchemy URL parsing.
    engine = create_engine(
        "postgresql+psycopg://",
        creator=lambda: psycopg.connect(url),
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline SQL generation is not supported; run against a database.")

run_migrations_online()
