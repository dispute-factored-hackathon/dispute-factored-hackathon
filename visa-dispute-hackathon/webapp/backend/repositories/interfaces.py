from typing import Protocol

from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.models.session import CustomerSession


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

    def list_by_customer(
        self,
        customer_id: str,
    ) -> list[Product]: ...


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
