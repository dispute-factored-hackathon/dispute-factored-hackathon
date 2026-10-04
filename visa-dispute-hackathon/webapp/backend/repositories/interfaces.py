from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from webapp.backend.models.call_center_interaction import CallCenterInteraction
from webapp.backend.models.call_transcript import CallTranscript
from webapp.backend.models.card_transaction import CardTransaction
from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.models.satisfaction_survey import SatisfactionSurvey
from webapp.backend.models.service_agent import ServiceAgent
from webapp.backend.models.session import CustomerSession
from webapp.backend.models.store import StoreProduct
from webapp.backend.models.transaction import Transaction


class CustomerRepository(Protocol):
    def create(
        self,
        customer: Customer,
    ) -> Customer: ...

    def get_by_id(
        self,
        customer_id: str,
    ) -> Customer | None: ...

    def get_by_document(
        self,
        document_number: str,
    ) -> Customer | None: ...

    def get_by_phone(
        self,
        mobile_phone: str,
    ) -> Customer | None: ...

    def search_by_full_name(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[Customer]: ...

    def update(
        self,
        customer: Customer,
    ) -> Customer: ...


class ProductRepository(Protocol):
    def create(
        self,
        product: Product,
    ) -> Product: ...

    def get_by_id(
        self,
        product_id: str,
    ) -> Product | None: ...

    def list_by_customer(
        self,
        customer_id: str,
    ) -> list[Product]: ...

    def update(
        self,
        product: Product,
    ) -> Product: ...


class TransactionRepository(Protocol):
    def create(
        self,
        transaction: Transaction,
    ) -> Transaction: ...

    def get_by_id(
        self,
        transaction_id: str,
    ) -> Transaction | None: ...

    def list_by_customer(
        self,
        customer_id: str,
    ) -> list[Transaction]: ...

    def update(
        self,
        transaction: Transaction,
    ) -> Transaction: ...


class ComplaintRepository(Protocol):
    def create(
        self,
        complaint: Complaint,
    ) -> Complaint: ...

    def get_by_id(
        self,
        complaint_id: str,
    ) -> Complaint | None: ...

    def list_by_customer(
        self,
        customer_id: str,
    ) -> list[Complaint]: ...

    def get_by_origin_interaction(
        self,
        customer_id: str,
        origin_interaction_id: str,
    ) -> Complaint | None: ...

    def update(
        self,
        complaint: Complaint,
    ) -> Complaint: ...


class SessionRepository(Protocol):
    def create(
        self,
        session: CustomerSession,
    ) -> CustomerSession: ...

    def get(
        self,
        session_id: str,
    ) -> CustomerSession | None: ...

    def delete(
        self,
        session_id: str,
    ) -> None: ...


class StoreCatalogRepository(Protocol):
    def list_all(self) -> list[StoreProduct]: ...

    def get_by_id(self, product_id: str) -> StoreProduct | None: ...


class ServiceAgentRepository(Protocol):
    def create(self, agent: ServiceAgent) -> ServiceAgent: ...
    def get_by_id(self, agent_id: str) -> ServiceAgent | None: ...
    def get_by_employee_code(self, employee_code: str) -> ServiceAgent | None: ...
    def update(self, agent: ServiceAgent) -> ServiceAgent: ...


class CallCenterInteractionRepository(Protocol):
    def create(self, interaction: CallCenterInteraction) -> CallCenterInteraction: ...
    def get_by_id(self, interaction_id: str) -> CallCenterInteraction | None: ...
    def list_by_customer(self, customer_id: str) -> list[CallCenterInteraction]: ...
    def update(self, interaction: CallCenterInteraction) -> CallCenterInteraction: ...


class CallTranscriptRepository(Protocol):
    def create(self, transcript: CallTranscript) -> CallTranscript: ...
    def get_by_interaction(self, interaction_id: str) -> CallTranscript | None: ...
    def update(self, transcript: CallTranscript) -> CallTranscript: ...


class SatisfactionSurveyRepository(Protocol):
    def create(self, survey: SatisfactionSurvey) -> SatisfactionSurvey: ...
    def get_by_interaction(self, interaction_id: str) -> SatisfactionSurvey | None: ...
    def list_by_agent(self, agent_id: str) -> list[SatisfactionSurvey]: ...


class CardPurchaseRepository(Protocol):
    """Card purchases joined with their card, always scoped to one customer."""

    def list_by_customer(self, customer_id: str, *, limit: int = 500) -> list[CardTransaction]: ...

    def get_for_customer(self, customer_id: str, transaction_id: str) -> CardTransaction | None: ...


def _no_resources() -> None:
    return None


@dataclass(frozen=True)
class Repositories:
    """Every repository the app needs, built once at startup and injected where used."""

    customers: CustomerRepository
    products: ProductRepository
    transactions: TransactionRepository
    complaints: ComplaintRepository
    sessions: SessionRepository
    service_agents: ServiceAgentRepository
    call_center_interactions: CallCenterInteractionRepository
    call_transcripts: CallTranscriptRepository
    satisfaction_surveys: SatisfactionSurveyRepository
    card_purchases: CardPurchaseRepository
    close: Callable[[], None] = field(default=_no_resources, repr=False, compare=False)
