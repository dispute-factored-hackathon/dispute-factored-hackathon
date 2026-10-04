import secrets
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    app_name: str = "Factored Bank"
    app_env: str = "development"
    log_level: str = "INFO"

    session_cookie_secure: bool = False
    session_duration_hours: int = 12
    demo_selector_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    # PostgreSQL (docker-compose.yml) is the only data store; it is filled from the lakehouse.
    # Application role (DML only). Never printed: SecretStr hides the password in repr/logs.
    database_url: SecretStr | None = None
    # Owner role used only by migrations and the data loaders; the web app never uses it.
    database_url_owner: SecretStr | None = None
    # Password given to the least-privilege application role when migrations create it.
    postgres_app_password: SecretStr | None = None
    database_pool_max_size: int = Field(default=10, ge=1, le=100)

    # Read-only source for dispute-db-seed-lakehouse (MotherDuck's Postgres endpoint).
    motherduck_token: SecretStr | None = None
    motherduck_pg_host: str = "pg.us-east-1-aws.motherduck.com"
    motherduck_pg_port: int = Field(default=5432, ge=1, le=65535)
    motherduck_database: str = "lakehouse"
    motherduck_schema: str = "silver"

    # Models for the Izzy web chat (read from .env; never logged).
    openai_api_key: SecretStr | None = None
    openai_agent_model: str = "gpt-4.1-mini"
    jev_api_key: SecretStr | None = None

    # Izzy's phone line, offered in the web app as the alternative channel (E.164).
    izzy_phone_number: str = Field(default="+16615779964", pattern=r"^\+[1-9]\d{7,14}$")
    # Izzy web chat limits: sessions are in memory and expire after inactivity.
    izzy_chat_session_ttl_minutes: int = Field(default=30, ge=1, le=24 * 60)
    izzy_chat_max_message_chars: int = Field(default=500, ge=50, le=4_000)
    izzy_chat_max_turns: int = Field(default=40, ge=1, le=500)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
