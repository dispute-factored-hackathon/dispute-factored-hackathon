"""The app lazily opens its only data store, PostgreSQL (no mock and no startup seed)."""

from dataclasses import replace

import fakes
import pytest
from fastapi.testclient import TestClient

from webapp.backend import main
from webapp.backend.api.dependencies import get_repositories
from webapp.backend.config import Settings
from webapp.backend.repositories.postgres import BackendConfigurationError
from webapp.backend.services import runtime


def test_public_pages_start_without_database_but_api_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(runtime, "get_settings", lambda: Settings(_env_file=None))
    main.app.dependency_overrides.pop(get_repositories, None)

    with TestClient(main.app) as client:
        assert client.get("/login").status_code == 200
        with pytest.raises(BackendConfigurationError, match=r"DATABASE_URL"):
            client.get("/api/auth/me")

    assert not hasattr(main.app.state, "repositories")


def test_first_api_opens_repositories_once_and_shutdown_closes_them(
    monkeypatch: pytest.MonkeyPatch,
):
    closed: list[bool] = []
    opened = fakes.new_repositories()
    tracked = replace(opened, close=lambda: closed.append(True))
    openings: list[bool] = []

    def open_once():
        openings.append(True)
        return tracked

    monkeypatch.setattr(runtime, "_open_repositories", open_once)
    main.app.dependency_overrides.pop(get_repositories, None)

    with TestClient(main.app) as client:
        assert main.app.state.repositories is None
        assert client.get("/login").status_code == 200
        assert main.app.state.repositories is None
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/api/auth/me").status_code == 401
        assert main.app.state.repositories is tracked
        assert openings == [True]
        assert closed == []

    assert closed == [True]
    assert not hasattr(main.app.state, "repositories")


def test_startup_does_not_create_any_customer(monkeypatch: pytest.MonkeyPatch):
    """Regression: five hardcoded demo customers used to be seeded on every start."""

    opened = fakes.new_repositories()
    monkeypatch.setattr(runtime, "_open_repositories", lambda: opened)
    main.app.dependency_overrides.pop(get_repositories, None)

    with TestClient(main.app) as client:
        options = client.get("/api/auth/demo-customers").json()["options"]

    assert options == []
    assert opened.customers.search_by_full_name("", limit=100) == []


def test_static_assets_do_not_initialize_data_or_chat_services():
    with TestClient(main.app) as client:
        assert client.get("/static/css/global.css").status_code == 200
        assert main.app.state.repositories is None
        assert main.app.state.izzy_chat is None
