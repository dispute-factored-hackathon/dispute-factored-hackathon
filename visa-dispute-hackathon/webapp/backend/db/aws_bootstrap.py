"""Idempotent Lambda entry point for schema migration and synthetic lakehouse seeding."""

from __future__ import annotations

from typing import Any

import psycopg

from webapp.backend.aws_runtime import configure_owner_runtime
from webapp.backend.config import get_settings
from webapp.backend.db.migrate import upgrade
from webapp.backend.db.seed_lakehouse import main as seed_lakehouse
from webapp.backend.repositories.postgres import open_repositories
from webapp.backend.services.izzy_agent import IZZY_AGENT_ID, seed_izzy_agent


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Upgrade the schema, refresh grants, and seed an idempotent demo sample."""
    del event, context
    configure_owner_runtime()
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.database_url_owner is not None
    owner_url = settings.database_url_owner.get_secret_value()
    app_password = (
        settings.postgres_app_password.get_secret_value()
        if settings.postgres_app_password
        else None
    )
    # Cloud deploy clients may retry a long synchronous invocation. Serialize the complete
    # migration/seed unit so two deliveries cannot race while creating Alembic metadata.
    with psycopg.connect(owner_url) as lock_connection:
        lock_connection.execute(
            "SELECT pg_advisory_lock(hashtext(%s))", ("factored-database-bootstrap",)
        )
        try:
            upgrade(owner_url, app_password, quiet=True)
            repositories = open_repositories(settings)
            try:
                seed_izzy_agent(repositories.service_agents)
            finally:
                repositories.close()
            seed_status = seed_lakehouse(["--customers", "100", "--allow-remote"])
            if seed_status != 0:
                raise RuntimeError("Lakehouse seed failed; inspect the migration Lambda logs")
        finally:
            lock_connection.execute(
                "SELECT pg_advisory_unlock(hashtext(%s))", ("factored-database-bootstrap",)
            )
    return {"status": "ready", "service_agent_id": IZZY_AGENT_ID}
