from threading import Lock

from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.models.session import CustomerSession


class MockCustomerRepository:
    def __init__(self) -> None:
        self._customers: dict[str, Customer] = {}
        self._lock = Lock()

    def create(
        self,
        customer: Customer,
    ) -> Customer:
        with self._lock:
            if self.get_by_document(customer.document_number) is not None:
                raise ValueError("FACTORED_ID already exists.")

            if customer.mobile_phone and self.get_by_phone(customer.mobile_phone) is not None:
                raise ValueError("Phone number already exists.")

            self._customers[customer.customer_id] = customer

        return customer

    def get_by_id(
        self,
        customer_id: str,
    ) -> Customer | None:
        return self._customers.get(customer_id)

    def get_by_document(
        self,
        document_number: str,
    ) -> Customer | None:
        return next(
            (
                customer
                for customer in self._customers.values()
                if customer.document_number == document_number
            ),
            None,
        )

    def get_by_phone(
        self,
        mobile_phone: str,
    ) -> Customer | None:
        return next(
            (
                customer
                for customer in self._customers.values()
                if customer.mobile_phone == mobile_phone
            ),
            None,
        )


class MockProductRepository:
    def __init__(self) -> None:
        self._products: dict[str, Product] = {}
        self._lock = Lock()

    def create(
        self,
        product: Product,
    ) -> Product:
        with self._lock:
            self._products[product.product_id] = product

        return product

    def get_by_id(
        self,
        product_id: str,
    ) -> Product | None:
        return self._products.get(product_id)

    def list_by_customer(
        self,
        customer_id: str,
    ) -> list[Product]:
        return [
            product for product in self._products.values() if product.customer_id == customer_id
        ]

    def update(
        self,
        product: Product,
    ) -> Product:
        with self._lock:
            if product.product_id not in self._products:
                raise ValueError("Product does not exist.")

            self._products[product.product_id] = product

        return product


class MockSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[
            str,
            CustomerSession,
        ] = {}

        self._lock = Lock()

    def create(
        self,
        session: CustomerSession,
    ) -> CustomerSession:
        with self._lock:
            self._sessions[session.session_id] = session

        return session

    def get(
        self,
        session_id: str,
    ) -> CustomerSession | None:
        return self._sessions.get(session_id)

    def delete(
        self,
        session_id: str,
    ) -> None:
        with self._lock:
            self._sessions.pop(
                session_id,
                None,
            )


customer_repository = MockCustomerRepository()

product_repository = MockProductRepository()

session_repository = MockSessionRepository()
