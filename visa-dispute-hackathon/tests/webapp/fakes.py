"""In-memory test doubles and hardcoded synthetic data for the web app tests.

The application only stores data in PostgreSQL. These doubles implement the same repository
contracts (`test_repository_contract.py` runs one suite against both) so route tests stay fast
and run without Docker. `conftest.py` injects them through `app.dependency_overrides`.
"""

import unicodedata
from datetime import UTC, date, datetime, timedelta
from threading import Lock

from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Accent, Customer, Gender
from webapp.backend.models.product import Product
from webapp.backend.models.session import CustomerSession
from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.interfaces import (
    CustomerRepository,
    ProductRepository,
    Repositories,
)


class InMemoryCustomerRepository:
    def __init__(self) -> None:
        self._customers: dict[str, Customer] = {}
        self._lock = Lock()

    def create(self, customer: Customer) -> Customer:
        with self._lock:
            if self.get_by_document(customer.document_number) is not None:
                raise ValueError("FACTORED_ID already exists.")

            if customer.mobile_phone and self.get_by_phone(customer.mobile_phone) is not None:
                raise ValueError("Phone number already exists.")

            self._customers[customer.customer_id] = customer

        return customer

    def get_by_id(self, customer_id: str) -> Customer | None:
        return self._customers.get(customer_id)

    def get_by_document(self, document_number: str) -> Customer | None:
        return next(
            (
                customer
                for customer in self._customers.values()
                if customer.document_number == document_number
            ),
            None,
        )

    def get_by_phone(self, mobile_phone: str) -> Customer | None:
        return next(
            (
                customer
                for customer in self._customers.values()
                if customer.mobile_phone == mobile_phone
            ),
            None,
        )

    def search_by_full_name(self, query: str, *, limit: int = 10) -> list[Customer]:
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

    def update(self, customer: Customer) -> Customer:
        with self._lock:
            if customer.customer_id not in self._customers:
                raise ValueError("Customer does not exist.")

            self._customers[customer.customer_id] = customer

        return customer


class InMemoryProductRepository:
    def __init__(self) -> None:
        self._products: dict[str, Product] = {}
        self._lock = Lock()

    def create(self, product: Product) -> Product:
        with self._lock:
            self._products[product.product_id] = product

        return product

    def get_by_id(self, product_id: str) -> Product | None:
        return self._products.get(product_id)

    def list_by_customer(self, customer_id: str) -> list[Product]:
        return [
            product for product in self._products.values() if product.customer_id == customer_id
        ]

    def update(self, product: Product) -> Product:
        with self._lock:
            if product.product_id not in self._products:
                raise ValueError("Product does not exist.")

            self._products[product.product_id] = product

        return product


class InMemoryTransactionRepository:
    def __init__(self) -> None:
        self._transactions: dict[str, Transaction] = {}
        self._lock = Lock()

    def create(self, transaction: Transaction) -> Transaction:
        with self._lock:
            self._transactions[transaction.transaction_id] = transaction

        return transaction

    def get_by_id(self, transaction_id: str) -> Transaction | None:
        return self._transactions.get(transaction_id)

    def list_by_customer(self, customer_id: str) -> list[Transaction]:
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

    def update(self, transaction: Transaction) -> Transaction:
        with self._lock:
            if transaction.transaction_id not in self._transactions:
                raise ValueError("Transaction does not exist.")

            self._transactions[transaction.transaction_id] = transaction

        return transaction


class InMemoryComplaintRepository:
    def __init__(self) -> None:
        self._complaints: dict[str, Complaint] = {}
        self._lock = Lock()

    def create(self, complaint: Complaint) -> Complaint:
        with self._lock:
            self._complaints[complaint.complaint_id] = complaint

        return complaint

    def get_by_id(self, complaint_id: str) -> Complaint | None:
        return self._complaints.get(complaint_id)

    def list_by_customer(self, customer_id: str) -> list[Complaint]:
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

    def update(self, complaint: Complaint) -> Complaint:
        with self._lock:
            if complaint.complaint_id not in self._complaints:
                raise ValueError("Complaint does not exist.")

            self._complaints[complaint.complaint_id] = complaint

        return complaint


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, CustomerSession] = {}
        self._lock = Lock()

    def create(self, session: CustomerSession) -> CustomerSession:
        with self._lock:
            self._sessions[session.session_id] = session

        return session

    def get(self, session_id: str) -> CustomerSession | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


def new_repositories() -> Repositories:
    return Repositories(
        customers=InMemoryCustomerRepository(),
        products=InMemoryProductRepository(),
        transactions=InMemoryTransactionRepository(),
        complaints=InMemoryComplaintRepository(),
        sessions=InMemorySessionRepository(),
    )


# Shared instances injected into the app by `conftest.py`; tests clear them between cases.
repositories = new_repositories()
customer_repository = repositories.customers
product_repository = repositories.products
transaction_repository = repositories.transactions
complaint_repository = repositories.complaints
session_repository = repositories.sessions


def clear_repositories() -> None:
    customer_repository._customers.clear()
    product_repository._products.clear()
    transaction_repository._transactions.clear()
    complaint_repository._complaints.clear()
    session_repository._sessions.clear()


# ----------------------------------------------------------------------------- synthetic data

DEMO_CUSTOMERS = (
    {
        "customer_id": "DEMO-BR-ANA-1001",
        "document_number": "410001",
        "first_name": "Ana Júlia",
        "last_name": "Santos",
        "country": "Brazil",
        "city": "São Paulo",
        "state": "SP",
        "accent": Accent.PORTUGUESE,
        "phone": "+5511900001001",
    },
    {
        "customer_id": "DEMO-BR-ANA-1002",
        "document_number": "410002",
        "first_name": "Ana Júlia",
        "last_name": "Santos",
        "country": "Brazil",
        "city": "Recife",
        "state": "PE",
        "accent": Accent.PORTUGUESE,
        "phone": "+5581900001002",
    },
    {
        "customer_id": "DEMO-CO-JOSE-2001",
        "document_number": "420001",
        "first_name": "José María",
        "last_name": "Pérez López",
        "country": "Colombia",
        "city": "Bogotá",
        "state": "Bogotá D.C.",
        "accent": Accent.COLOMBIAN_SPANISH,
        "phone": "+573009000001",
    },
    {
        "customer_id": "DEMO-MX-XIMENA-3001",
        "document_number": "430001",
        "first_name": "Ximena",
        "last_name": "Hernández Ruiz",
        "country": "Mexico",
        "city": "Ciudad de México",
        "state": "CDMX",
        "accent": Accent.MEXICAN_SPANISH,
        "phone": "+525590000001",
    },
    {
        "customer_id": "DEMO-US-JORDAN-4001",
        "document_number": "440001",
        "first_name": "Jordan",
        "last_name": "Taylor",
        "country": "United States",
        "city": "Austin",
        "state": "TX",
        "accent": Accent.ENGLISH,
        "phone": "+15129000001",
    },
)


def seed_demo_customers(
    customers: CustomerRepository,
    products: ProductRepository | None = None,
) -> None:
    """Dataset-like customers (not judges): each has one active credit card."""

    now = datetime.now(UTC)
    for data in DEMO_CUSTOMERS:
        if not customers.get_by_id(data["customer_id"]):
            customers.create(
                Customer(
                    customer_id=data["customer_id"],
                    document_number=data["document_number"],
                    document_type="DEMO_ID",
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    date_of_birth=date(1990, 1, 1),
                    gender=Gender.PREFER_NOT_TO_SAY,
                    mobile_phone=data["phone"],
                    city=data["city"],
                    state=data["state"],
                    country=data["country"],
                    detected_accent=data["accent"],
                    segment="Hackathon demo",
                    registration_date=now,
                    registration_branch_id=1,
                    customer_status="Active",
                    onboarding_completed=True,
                    last_updated=now,
                )
            )
        if products and not products.list_by_customer(data["customer_id"]):
            products.create(
                Product(
                    product_id=f"CARD-{data['customer_id']}",
                    customer_id=data["customer_id"],
                    product_type="Credit Card",
                    product_number=f"4111111111{data['document_number']}",
                    currency="USD",
                    current_balance=0.0,
                    credit_limit=10_000.0,
                    opening_date=now.date(),
                    opening_branch_id=1,
                    product_status="Active",
                    opening_channel="Web",
                    has_linked_app=True,
                    last_updated=now,
                )
            )


HISTORY_TRANSACTIONS = (
    {
        "days_ago": 1,
        "merchant_name": "Factored Coffee",
        "merchant_category": "Coffee Shop",
        "transaction_category": "Food & Drink",
        "amount": 8.75,
        "channel": "POS",
        "country": "Factoredland",
        "city": "Factored Village",
        "is_fraud": False,
        "fraud_score": 0.03,
    },
    {
        "days_ago": 3,
        "merchant_name": "StreamBox",
        "merchant_category": "Digital Services",
        "transaction_category": "Entertainment",
        "amount": 14.99,
        "channel": "Web",
        "country": "Factoredland",
        "city": "Factored Village",
        "is_fraud": False,
        "fraud_score": 0.08,
    },
    {
        "days_ago": 5,
        "merchant_name": "Mercado Central",
        "merchant_category": "Grocery Store",
        "transaction_category": "Groceries",
        "amount": 73.42,
        "channel": "POS",
        "country": "Factoredland",
        "city": "Factored Village",
        "is_fraud": False,
        "fraud_score": 0.05,
    },
    {
        "days_ago": 7,
        "merchant_name": "Shady Business",
        "merchant_category": "Online Retail",
        "transaction_category": "Suspicious Purchase",
        "amount": 129.90,
        "channel": "Web",
        "country": "Unknown",
        "city": "Unknown",
        "is_fraud": True,
        "fraud_score": 0.94,
    },
)


def add_history(customer_id: str) -> None:
    """Give a customer four card transactions and two complaints (one open, one resolved).

    Signup no longer creates history, so tests that read transactions or complaints add it here.
    """

    customer = customer_repository.get_by_id(customer_id)
    assert customer is not None, "create the customer before adding history"
    product = product_repository.list_by_customer(customer_id)[0]
    now = datetime.now(UTC)

    for index, data in enumerate(HISTORY_TRANSACTIONS, start=1):
        transaction_date = now - timedelta(days=data["days_ago"])
        transaction_repository.create(
            Transaction(
                transaction_id=f"TRX-TEST-{customer_id}-{index}",
                transaction_date=transaction_date,
                process_date=transaction_date.date(),
                product_id=product.product_id,
                customer_id=customer_id,
                transaction_type="Purchase",
                transaction_category=data["transaction_category"],
                amount=data["amount"],
                currency="USD",
                amount_usd=data["amount"],
                channel=data["channel"],
                branch_id=None,
                merchant_name=data["merchant_name"],
                merchant_category=data["merchant_category"],
                transaction_country=data["country"],
                transaction_city=data["city"],
                transaction_status="Approved",
                response_code="00",
                is_fraud=data["is_fraud"],
                fraud_score=data["fraud_score"],
                latitude=None,
                longitude=None,
            )
        )

    resolved_creation = now - timedelta(days=45)
    complaint_repository.create(
        Complaint(
            complaint_id=f"CMP-TEST-{customer_id}-RESOLVED",
            creation_date=resolved_creation,
            process_date=resolved_creation.date(),
            customer_id=customer_id,
            case_type="Claim",
            category="Card Purchase",
            subcategory="Duplicate Charge",
            reception_channel="Web",
            affected_product_id=product.product_id,
            related_branch_id=None,
            origin_interaction_id=None,
            description="Customer reported a duplicate charge from Factored Coffee.",
            claimed_amount=8.75,
            currency="USD",
            priority="Medium",
            status="Resolved",
            assigned_agent_id="IZZY",
            assignment_date=resolved_creation + timedelta(hours=1),
            first_response_date=resolved_creation + timedelta(hours=2),
            resolution_date=resolved_creation + timedelta(days=2),
            closing_date=resolved_creation + timedelta(days=3),
            sla_breached=False,
            resolution_days=2,
            resolution="Duplicate charge confirmed. The disputed amount was refunded.",
            compensation_granted=8.75,
            resolution_satisfaction=5.0,
            is_repeat_complainer=False,
        )
    )

    open_creation = now - timedelta(days=4)
    complaint_repository.create(
        Complaint(
            complaint_id=f"CMP-TEST-{customer_id}-OPEN",
            creation_date=open_creation,
            process_date=open_creation.date(),
            customer_id=customer_id,
            case_type="Claim",
            category="Card Purchase",
            subcategory="Unrecognized Transaction",
            reception_channel="Call Center",
            affected_product_id=product.product_id,
            related_branch_id=None,
            origin_interaction_id=None,
            description="Customer reported an unrecognized online purchase and requested review.",
            claimed_amount=129.90,
            currency="USD",
            priority="High",
            status="In Review",
            assigned_agent_id="IZZY",
            assignment_date=open_creation + timedelta(minutes=10),
            first_response_date=open_creation + timedelta(minutes=15),
            resolution_date=None,
            closing_date=None,
            sla_breached=False,
            resolution_days=None,
            resolution=None,
            compensation_granted=None,
            resolution_satisfaction=None,
            is_repeat_complainer=True,
        )
    )
