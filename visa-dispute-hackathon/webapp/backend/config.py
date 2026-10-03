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
    motherduck_database: str = "lakehouse"
    motherduck_schema: str = "silver"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
