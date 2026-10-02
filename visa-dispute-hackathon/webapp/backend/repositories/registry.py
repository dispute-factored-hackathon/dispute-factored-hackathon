"""Selects the repository backend once, at import time, from `REPOSITORY_BACKEND`.

Routes and services import their repositories from here instead of from `mock.py`:

* ``mock`` (default): the in-memory singletons from `mock.py`, exactly as before.
* ``postgres``: PostgreSQL from docker-compose.yml, created through the same contracts.
"""

from dataclasses import dataclass

from webapp.backend.config import Settings, get_settings
from webapp.backend.repositories import mock
from webapp.backend.repositories.interfaces import (
    CallCenterInteractionRepository,
    CallTranscriptRepository,
    ComplaintRepository,
    CustomerRepository,
    ProductRepository,
    SatisfactionSurveyRepository,
    ServiceAgentRepository,
    SessionRepository,
    TransactionRepository,
)


class BackendConfigurationError(RuntimeError):
    """The selected backend cannot start. Messages never include credentials."""


@dataclass(frozen=True)
class Repositories:
    customers: CustomerRepository
    products: ProductRepository
    transactions: TransactionRepository
    complaints: ComplaintRepository
    sessions: SessionRepository
    service_agents: ServiceAgentRepository
    call_center_interactions: CallCenterInteractionRepository
    call_transcripts: CallTranscriptRepository
    satisfaction_surveys: SatisfactionSurveyRepository
    database: object | None = None  # the pooled Database for postgres, None for mock

    def close(self) -> None:
        close = getattr(self.database, "close", None)
        if close is not None:
            close()


def build_repositories(settings: Settings) -> Repositories:
    if settings.repository_backend == "mock":
        return Repositories(
            customers=mock.customer_repository,
            products=mock.product_repository,
            transactions=mock.transaction_repository,
            complaints=mock.complaint_repository,
            sessions=mock.session_repository,
            service_agents=mock.service_agent_repository,
            call_center_interactions=mock.call_center_interaction_repository,
            call_transcripts=mock.call_transcript_repository,
            satisfaction_surveys=mock.satisfaction_survey_repository,
        )

    # Imported lazily so the default mock backend never opens a database connection.
    from webapp.backend.db.database import Database
    from webapp.backend.db.migrate import expected_revision
    from webapp.backend.repositories import postgres

    if settings.database_url is None:
        raise BackendConfigurationError(
            "REPOSITORY_BACKEND=postgres requires DATABASE_URL (the factored_app role). "
            "See .env.example."
        )
    database = Database(
        settings.database_url.get_secret_value(), max_size=settings.database_pool_max_size
    )
    database.open()
    try:
        database.check_migrated(expected_revision())
    except Exception:
        database.close()
        raise
    return Repositories(
        customers=postgres.PostgresCustomerRepository(database),
        products=postgres.PostgresProductRepository(database),
        transactions=postgres.PostgresTransactionRepository(database),
        complaints=postgres.PostgresComplaintRepository(database),
        sessions=postgres.PostgresSessionRepository(database),
        service_agents=postgres.PostgresServiceAgentRepository(database),
        call_center_interactions=postgres.PostgresCallCenterInteractionRepository(database),
        call_transcripts=postgres.PostgresCallTranscriptRepository(database),
        satisfaction_surveys=postgres.PostgresSatisfactionSurveyRepository(database),
        database=database,
    )


_repositories = build_repositories(get_settings())
repository_backend = get_settings().repository_backend

customer_repository = _repositories.customers
product_repository = _repositories.products
transaction_repository = _repositories.transactions
complaint_repository = _repositories.complaints
session_repository = _repositories.sessions
service_agent_repository = _repositories.service_agents
call_center_interaction_repository = _repositories.call_center_interactions
call_transcript_repository = _repositories.call_transcripts
satisfaction_survey_repository = _repositories.satisfaction_surveys


def close_repositories() -> None:
    """Release database connections on shutdown (a no-op for the mock backend)."""

    _repositories.close()
