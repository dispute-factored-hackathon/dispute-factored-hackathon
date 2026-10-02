import unicodedata
from threading import Lock

from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.models.session import CustomerSession
from webapp.backend.models.store import StoreProduct
from webapp.backend.models.transaction import Transaction


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

    def search_by_full_name(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[Customer]:
        normalized_query = self._normalize_name(query)
        customers = sorted(
            self._customers.values(),
            key=lambda customer: self._normalize_name(
                f"{customer.first_name} {customer.last_name}"
            ),
        )
        if normalized_query:
            customers = [
                customer
                for customer in customers
                if normalized_query
                in self._normalize_name(f"{customer.first_name} {customer.last_name}")
            ]
        return customers[:limit]

    @staticmethod
    def _normalize_name(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        without_marks = "".join(
            character for character in decomposed if not unicodedata.combining(character)
        )
        return " ".join(without_marks.split())

    def update(
        self,
        customer: Customer,
    ) -> Customer:
        with self._lock:
            if customer.customer_id not in self._customers:
                raise ValueError("Customer does not exist.")

            self._customers[customer.customer_id] = customer

        return customer


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


class MockTransactionRepository:
    def __init__(self) -> None:
        self._transactions: dict[
            str,
            Transaction,
        ] = {}

        self._lock = Lock()

    def create(
        self,
        transaction: Transaction,
    ) -> Transaction:
        with self._lock:
            self._transactions[transaction.transaction_id] = transaction

        return transaction

    def get_by_id(
        self,
        transaction_id: str,
    ) -> Transaction | None:
        return self._transactions.get(transaction_id)

    def list_by_customer(
        self,
        customer_id: str,
    ) -> list[Transaction]:
        transactions = [
            transaction
            for transaction in self._transactions.values()
            if transaction.customer_id == customer_id
        ]

        return sorted(
            transactions,
            key=lambda transaction: transaction.transaction_date,
            reverse=True,
        )

    def update(
        self,
        transaction: Transaction,
    ) -> Transaction:
        with self._lock:
            if transaction.transaction_id not in self._transactions:
                raise ValueError("Transaction does not exist.")

            self._transactions[transaction.transaction_id] = transaction

        return transaction


class MockComplaintRepository:
    def __init__(self) -> None:
        self._complaints: dict[
            str,
            Complaint,
        ] = {}

        self._lock = Lock()

    def create(
        self,
        complaint: Complaint,
    ) -> Complaint:
        with self._lock:
            if complaint.complaint_id in self._complaints:
                raise ValueError("Complaint already exists.")
            self._complaints[complaint.complaint_id] = complaint

        return complaint

    def get_by_id(
        self,
        complaint_id: str,
    ) -> Complaint | None:
        return self._complaints.get(complaint_id)

    def list_by_customer(
        self,
        customer_id: str,
    ) -> list[Complaint]:
        complaints = [
            complaint
            for complaint in self._complaints.values()
            if complaint.customer_id == customer_id
        ]

        return sorted(
            complaints,
            key=lambda complaint: complaint.creation_date,
            reverse=True,
        )

    def get_by_origin_interaction(
        self,
        customer_id: str,
        origin_interaction_id: str,
    ) -> Complaint | None:
        return next(
            (
                complaint
                for complaint in self._complaints.values()
                if complaint.customer_id == customer_id
                and complaint.origin_interaction_id == origin_interaction_id
            ),
            None,
        )

    def update(
        self,
        complaint: Complaint,
    ) -> Complaint:
        with self._lock:
            if complaint.complaint_id not in self._complaints:
                raise ValueError("Complaint does not exist.")

            self._complaints[complaint.complaint_id] = complaint

        return complaint


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


class MockStoreCatalogRepository:
    def __init__(self, products: tuple[StoreProduct, ...]) -> None:
        self._products = {product.product_id: product for product in products}

    def list_all(self) -> list[StoreProduct]:
        return list(self._products.values())

    def get_by_id(self, product_id: str) -> StoreProduct | None:
        return self._products.get(product_id)


customer_repository = MockCustomerRepository()

product_repository = MockProductRepository()

transaction_repository = MockTransactionRepository()

complaint_repository = MockComplaintRepository()

session_repository = MockSessionRepository()
