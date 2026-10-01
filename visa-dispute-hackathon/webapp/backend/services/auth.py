import base64
import hashlib
import hmac
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

        return customer, self._create_session(customer)

    def list_demo_options(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[tuple[Customer, str]]:
        active_options = [
            (customer, self._selection_for(customer.customer_id))
            for customer in self.customers.search_by_full_name(query, limit=100)
            if customer.customer_status == "Active"
        ]
        return active_options[:limit]

    def login_demo_selection(
        self,
        selection: str,
    ) -> tuple[Customer, CustomerSession]:
        customer_id = self._customer_id_from_selection(selection)
        customer = self.customers.get_by_id(customer_id) if customer_id else None
        if customer is None or customer.customer_status != "Active":
            raise AuthenticationError(
                "That demo profile is no longer available. Search for the customer again."
            )
        return self.login(customer.document_number)

    def _create_session(self, customer: Customer) -> CustomerSession:
        now = datetime.now(UTC)
        session = CustomerSession(
            session_id=secrets.token_urlsafe(32),
            customer_id=customer.customer_id,
            created_at=now,
            expires_at=now + timedelta(hours=settings.session_duration_hours),
        )
        self.sessions.create(session)
        return session

    def _selection_for(self, customer_id: str) -> str:
        encoded = base64.urlsafe_b64encode(customer_id.encode()).decode().rstrip("=")
        signature = hmac.new(
            settings.demo_selector_secret.encode(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        return f"{encoded}.{signature}"

    def _customer_id_from_selection(self, selection: str) -> str | None:
        try:
            encoded, supplied_signature = selection.split(".", maxsplit=1)
            expected_signature = hmac.new(
                settings.demo_selector_secret.encode(), encoded.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                return None
            padding = "=" * (-len(encoded) % 4)
            return base64.urlsafe_b64decode(encoded + padding).decode()
        except (ValueError, UnicodeDecodeError):
            return None

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
