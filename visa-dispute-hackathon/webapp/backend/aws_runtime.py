"""Load AWS runtime secrets without exposing credentials in Lambda variables."""

from __future__ import annotations

import hashlib
import json
import os
from functools import cache
from urllib.parse import quote_plus


class AwsRuntimeConfigurationError(RuntimeError):
    """Raised when an AWS runtime secret or database setting is incomplete."""


@cache
def load_json_secret(secret_arn: str) -> dict[str, str]:
    """Return one Secrets Manager JSON object, cached for the warm environment."""
    import boto3

    response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
    try:
        value = json.loads(response["SecretString"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise AwsRuntimeConfigurationError("AWS secret is not a JSON object") from error
    if not isinstance(value, dict):
        raise AwsRuntimeConfigurationError("AWS secret is not a JSON object")
    return {str(key): str(item) for key, item in value.items()}


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AwsRuntimeConfigurationError(f"{name} is not configured")
    return value


def _required_secret(secret: dict[str, str], name: str) -> str:
    value = secret.get(name, "").strip()
    if not value:
        raise AwsRuntimeConfigurationError(f"AWS secret is missing {name}")
    return value


def postgres_url(*, username: str, password: str) -> str:
    """Build a TLS PostgreSQL URL from non-secret Lambda settings and a secret password."""
    host = _required_environment("DATABASE_HOST")
    port = _required_environment("DATABASE_PORT")
    database = _required_environment("DATABASE_NAME")
    return (
        f"postgresql://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/"
        f"{quote_plus(database)}?sslmode=require"
    )


def configure_application_runtime() -> None:
    """Configure least-privilege database and AI credentials for web/voice runtimes."""
    app_secret = load_json_secret(_required_environment("DATABASE_APP_SECRET_ARN"))
    app_username = _required_secret(app_secret, "username")
    app_password = _required_secret(app_secret, "password")
    os.environ["DATABASE_URL"] = postgres_url(username=app_username, password=app_password)

    # A stable, non-exported derivation is sufficient for signing synthetic demo selectors.
    os.environ.setdefault(
        "DEMO_SELECTOR_SECRET",
        hashlib.sha256(f"factored-selector:{app_password}".encode()).hexdigest(),
    )

    motherduck_arn = os.environ.get("MOTHERDUCK_SECRET_ARN", "").strip()
    if motherduck_arn:
        motherduck = load_json_secret(motherduck_arn)
        os.environ["MOTHERDUCK_TOKEN"] = _required_secret(motherduck, "MOTHERDUCK_TOKEN")

    openai_arn = os.environ.get("OPENAI_SECRET_ARN", "").strip()
    if openai_arn:
        openai = load_json_secret(openai_arn)
        for name in ("OPENAI_API_KEY", "JEV_API_KEY", "OPENAI_WEBHOOK_SECRET"):
            if value := openai.get(name, "").strip():
                os.environ[name] = value

    langsmith_arn = os.environ.get("LANGSMITH_SECRET_ARN", "").strip()
    if langsmith_arn:
        langsmith = load_json_secret(langsmith_arn)
        os.environ["LANGSMITH_API_KEY"] = _required_secret(langsmith, "LANGSMITH_API_KEY")


def configure_owner_runtime() -> None:
    """Configure owner and application credentials for migrations and seeding only."""
    owner = load_json_secret(_required_environment("DATABASE_OWNER_SECRET_ARN"))
    app = load_json_secret(_required_environment("DATABASE_APP_SECRET_ARN"))
    owner_url = postgres_url(
        username=_required_secret(owner, "username"),
        password=_required_secret(owner, "password"),
    )
    app_password = _required_secret(app, "password")
    os.environ["DATABASE_URL_OWNER"] = owner_url
    os.environ["POSTGRES_APP_PASSWORD"] = app_password
    os.environ["DATABASE_URL"] = postgres_url(
        username=_required_secret(app, "username"), password=app_password
    )

    motherduck = load_json_secret(_required_environment("MOTHERDUCK_SECRET_ARN"))
    os.environ["MOTHERDUCK_TOKEN"] = _required_secret(motherduck, "MOTHERDUCK_TOKEN")
