"""The app's only data store is PostgreSQL, opened by the lifespan (no mock, no startup seed)."""

from dataclasses import replace

import fakes
import pytest
from fastapi.testclient import TestClient

from webapp.backend import main
from webapp.backend.api.dependencies import get_repositories
from webapp.backend.config import Settings
from webapp.backend.repositories.postgres import BackendConfigurationError


def test_startup_refuses_to_run_without_a_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "settings", Settings(_env_file=None))

    with pytest.raises(BackendConfigurationError, match=r"DATABASE_URL"), TestClient(main.app):
        pass

    assert not hasattr(main.app.state, "repositories")


def test_lifespan_opens_the_repositories_and_closes_them_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
):
    closed: list[bool] = []
    opened = fakes.new_repositories()
    tracked = replace(opened, close=lambda: closed.append(True))
    monkeypatch.setattr(main, "open_repositories", lambda settings: tracked)
    main.app.dependency_overrides.pop(get_repositories, None)

    with TestClient(main.app) as client:
        assert main.app.state.repositories is tracked
        assert client.get("/api/auth/me").status_code == 401
        assert closed == []

    assert closed == [True]
    assert not hasattr(main.app.state, "repositories")


def test_startup_does_not_create_any_customer(monkeypatch: pytest.MonkeyPatch):
    """Regression: five hardcoded demo customers used to be seeded on every start."""

    opened = fakes.new_repositories()
    monkeypatch.setattr(main, "open_repositories", lambda settings: opened)
    main.app.dependency_overrides.pop(get_repositories, None)

    with TestClient(main.app) as client:
        options = client.get("/api/auth/demo-customers").json()["options"]

    assert options == []
    assert opened.customers.search_by_full_name("", limit=100) == []


def test_requests_fail_loudly_when_the_repositories_were_never_opened():
    main.app.dependency_overrides.pop(get_repositories, None)
    client = TestClient(main.app, raise_server_exceptions=True)
    client.cookies.set("factored_session", "anything")

    with pytest.raises(RuntimeError, match=r"not opened at application startup"):
        client.get("/api/auth/me")
