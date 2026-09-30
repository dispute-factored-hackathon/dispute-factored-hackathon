from typing import Protocol

from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.models.session import CustomerSession
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
