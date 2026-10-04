import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from webapp.backend.config import get_settings
from webapp.backend.models.customer import Customer
from webapp.backend.models.session import AuthenticationMethod, CustomerSession
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

        return customer, self._create_session(
            customer,
            AuthenticationMethod.FACTORED_ID,
        )

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
        return customer, self._create_session(
            customer,
            AuthenticationMethod.DEMO_SELECTOR,
        )

    def _create_session(
        self,
        customer: Customer,
        authentication_method: AuthenticationMethod,
    ) -> CustomerSession:
        now = datetime.now(UTC)
        session = CustomerSession(
            session_id="",
            customer_id=customer.customer_id,
            authentication_method=authentication_method,
            created_at=now,
            expires_at=now + timedelta(hours=settings.session_duration_hours),
        )
        session = session.model_copy(update={"session_id": self._signed_session_id(session)})
        self.sessions.create(session)
        return session

    def _signed_session_id(self, session: CustomerSession) -> str:
        """Create an integrity-protected demo session that survives Lambda cold starts."""
        payload = {
            "authentication_method": session.authentication_method.value,
            "created_at": int(session.created_at.timestamp()),
            "customer_id": session.customer_id,
            "expires_at": int(session.expires_at.timestamp()),
            "nonce": secrets.token_urlsafe(12),
        }
        encoded = (
            base64.urlsafe_b64encode(
                json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
            )
            .decode()
            .rstrip("=")
        )
        signature = hmac.new(
            settings.demo_selector_secret.encode(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        return f"v1.{encoded}.{signature}"

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
        authenticated = self.authenticate_with_session(session_id)
        return authenticated[0] if authenticated else None

    def authenticate_with_session(
        self,
        session_id: str,
    ) -> tuple[Customer, CustomerSession] | None:
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

        return customer, session

    def logout(
        self,
        session_id: str,
    ) -> None:
        self.sessions.delete(session_id)
