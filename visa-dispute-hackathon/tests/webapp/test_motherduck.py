from psycopg.conninfo import conninfo_to_dict

from webapp.backend.config import Settings
from webapp.backend.db import motherduck


def test_lakehouse_connection_uses_configured_port(monkeypatch):
    captured: dict[str, str] = {}
    connection = object()

    def fake_connect(dsn: str, **_kwargs):
        captured.update(conninfo_to_dict(dsn))
        return connection

    monkeypatch.setattr(motherduck.psycopg, "connect", fake_connect)
    settings = Settings(
        _env_file=None,
        motherduck_token="synthetic-test-token",
        motherduck_pg_host="lakehouse.example.test",
        motherduck_pg_port=6543,
        motherduck_database="synthetic",
    )

    assert motherduck.connect_lakehouse(settings) is connection
    assert captured["host"] == "lakehouse.example.test"
    assert captured["port"] == "6543"
    assert captured["dbname"] == "synthetic"
    assert captured["password"] == "synthetic-test-token"


def test_lakehouse_target_includes_configured_port():
    settings = Settings(
        _env_file=None,
        motherduck_pg_host="lakehouse.example.test",
        motherduck_pg_port=6543,
        motherduck_database="synthetic",
    )

    assert motherduck.lakehouse_target(settings) == "lakehouse.example.test:6543/synthetic"
