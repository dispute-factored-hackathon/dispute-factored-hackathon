import secrets
from datetime import UTC, datetime, timedelta

from webapp.backend.config import get_settings
from webapp.backend.models.customer import Customer
from webapp.backend.models.session import CustomerSession
from webapp.backend.repositories.interfaces import (
    CustomerRepository,
    SessionRepository,
)

settings = get_settings()


class AuthenticationError(Exception):
    pass


class AuthenticationService:
    def __init__(
        self,
        customers: CustomerRepository,
        sessions: SessionRepository,
    ) -> None:
        self.customers = customers
        self.sessions = sessions

    def login(
        self,
        factored_id: str,
    ) -> tuple[
        Customer,
        CustomerSession,
    ]:
        customer = self.customers.get_by_document(factored_id)

        if customer is None or customer.customer_status != "Active":
            raise AuthenticationError(
                "We could not find an active Factored Bank demo account with this Factored ID."
            )

        now = datetime.now(UTC)

        session = CustomerSession(
            session_id=secrets.token_urlsafe(32),
            customer_id=customer.customer_id,
            created_at=now,
            expires_at=(now + timedelta(hours=(settings.session_duration_hours))),
        )

        self.sessions.create(session)

        return customer, session

    def authenticate(
        self,
        session_id: str,
    ) -> Customer | None:
        session = self.sessions.get(session_id)

        if session is None:
            return None

        now = datetime.now(UTC)

        if session.expires_at <= now:
            self.sessions.delete(session_id)
            return None

        customer = self.customers.get_by_id(session.customer_id)

        if customer is None or customer.customer_status != "Active":
            self.sessions.delete(session_id)
            return None

        return customer

    def logout(
        self,
        session_id: str,
    ) -> None:
        self.sessions.delete(session_id)
