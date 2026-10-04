from types import SimpleNamespace
from unittest.mock import patch

from pydantic import SecretStr

from webapp.backend import aws_runtime
from webapp.backend.db import aws_bootstrap


def test_application_runtime_builds_encoded_least_privilege_url(monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "private.cluster")
    monkeypatch.setenv("DATABASE_PORT", "5432")
    monkeypatch.setenv("DATABASE_NAME", "factored")
    monkeypatch.setenv("DATABASE_APP_SECRET_ARN", "app-secret")
    monkeypatch.setenv("MOTHERDUCK_SECRET_ARN", "lakehouse-secret")
    monkeypatch.setenv("OPENAI_SECRET_ARN", "openai-secret")
    monkeypatch.setenv("LANGSMITH_SECRET_ARN", "langsmith-secret")
    secrets = {
        "app-secret": {"username": "factored_app", "password": "a password/+"},
        "lakehouse-secret": {"MOTHERDUCK_TOKEN": "motherduck"},
        "openai-secret": {"OPENAI_API_KEY": "openai", "JEV_API_KEY": "jev"},
        "langsmith-secret": {"LANGSMITH_API_KEY": "langsmith"},
    }
    with patch.object(aws_runtime, "load_json_secret", side_effect=secrets.__getitem__):
        aws_runtime.configure_application_runtime()

    assert (
        aws_runtime.os.environ["DATABASE_URL"]
        == "postgresql://factored_app:a+password%2F%2B@private.cluster:5432/factored?sslmode=require"
    )
    assert aws_runtime.os.environ["MOTHERDUCK_TOKEN"] == "motherduck"
    assert aws_runtime.os.environ["OPENAI_API_KEY"] == "openai"
    assert len(aws_runtime.os.environ["DEMO_SELECTOR_SECRET"]) == 64
    for name in (
        "DATABASE_URL",
        "MOTHERDUCK_TOKEN",
        "OPENAI_API_KEY",
        "JEV_API_KEY",
        "DEMO_SELECTOR_SECRET",
        "LANGSMITH_API_KEY",
    ):
        aws_runtime.os.environ.pop(name, None)


def test_database_bootstrap_migrates_before_idempotent_remote_seed():
    settings = SimpleNamespace(
        database_url_owner=SecretStr("postgresql://owner:secret@db/factored"),
        postgres_app_password=SecretStr("app-password"),
    )
    with (
        patch.object(aws_bootstrap, "configure_owner_runtime"),
        patch.object(aws_bootstrap, "get_settings", return_value=settings),
        patch.object(aws_bootstrap.psycopg, "connect") as connect,
        patch.object(aws_bootstrap, "upgrade") as upgrade,
        patch.object(aws_bootstrap, "seed_lakehouse", return_value=0) as seed,
    ):
        result = aws_bootstrap.lambda_handler({}, object())

    assert result == {"status": "ready"}
    upgrade.assert_called_once_with(
        "postgresql://owner:secret@db/factored", "app-password", quiet=True
    )
    seed.assert_called_once_with(["--customers", "100", "--allow-remote"])
    connection = connect.return_value.__enter__.return_value
    assert connection.execute.call_count == 2
