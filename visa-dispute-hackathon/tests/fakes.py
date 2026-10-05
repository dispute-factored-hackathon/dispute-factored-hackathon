"""In-memory test doubles and hardcoded synthetic data for the web and voice tests.

The application only stores data in PostgreSQL. These doubles implement the same repository
contracts (`webapp/test_repository_contract.py` runs one suite against both) so tests stay fast
and run without Docker. The web app receives them through `app.dependency_overrides`; voice tests
pass them to `VoiceCallService` and `SipRealtimeGateway`.
"""

import random
import unicodedata
from datetime import UTC, date, datetime, timedelta
from threading import Lock
from typing import Any

from webapp.backend.models.call_center_interaction import CallCenterInteraction
from webapp.backend.models.call_transcript import CallTranscript
from webapp.backend.models.card_transaction import (
    CARD_PRODUCT_TYPES,
    CARD_PURCHASE_TYPE,
    CardTransaction,
)
from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Accent, Customer, Gender
from webapp.backend.models.product import Product
from webapp.backend.models.satisfaction_survey import SatisfactionSurvey
from webapp.backend.models.service_agent import ServiceAgent
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
        digits = "".join(character for character in mobile_phone if character.isdigit())
        if not digits:
            return None
        return next(
            (
                customer
                for customer in self._customers.values()
                if customer.mobile_phone
                and "".join(character for character in customer.mobile_phone if character.isdigit())
                == digits
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
            if complaint.complaint_id in self._complaints:
                raise ValueError("Complaint already exists.")
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

    def get_by_origin_interaction(
        self, customer_id: str, origin_interaction_id: str
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


class InMemoryServiceAgentRepository:
    def __init__(self) -> None:
        self._agents: dict[str, ServiceAgent] = {}
        self._lock = Lock()

    def create(self, agent: ServiceAgent) -> ServiceAgent:
        with self._lock:
            if agent.agent_id in self._agents or self.get_by_employee_code(agent.employee_code):
                raise ValueError("Service agent already exists.")
            self._agents[agent.agent_id] = agent
        return agent

    def get_by_id(self, agent_id: str) -> ServiceAgent | None:
        return self._agents.get(agent_id)

    def get_by_employee_code(self, employee_code: str) -> ServiceAgent | None:
        return next((a for a in self._agents.values() if a.employee_code == employee_code), None)

    def update(self, agent: ServiceAgent) -> ServiceAgent:
        with self._lock:
            if agent.agent_id not in self._agents:
                raise ValueError("Service agent does not exist.")
            self._agents[agent.agent_id] = agent
        return agent


class InMemoryCallCenterInteractionRepository:
    def __init__(self) -> None:
        self._interactions: dict[str, CallCenterInteraction] = {}
        self._lock = Lock()

    def create(self, interaction: CallCenterInteraction) -> CallCenterInteraction:
        with self._lock:
            if interaction.interaction_id in self._interactions:
                raise ValueError("Interaction already exists.")
            self._interactions[interaction.interaction_id] = interaction
        return interaction

    def get_by_id(self, interaction_id: str) -> CallCenterInteraction | None:
        return self._interactions.get(interaction_id)

    def list_by_customer(self, customer_id: str) -> list[CallCenterInteraction]:
        return sorted(
            (item for item in self._interactions.values() if item.customer_id == customer_id),
            key=lambda item: item.interaction_date,
            reverse=True,
        )

    def update(self, interaction: CallCenterInteraction) -> CallCenterInteraction:
        with self._lock:
            if interaction.interaction_id not in self._interactions:
                raise ValueError("Interaction does not exist.")
            self._interactions[interaction.interaction_id] = interaction
        return interaction


class InMemoryCallTranscriptRepository:
    def __init__(self) -> None:
        self._transcripts: dict[str, CallTranscript] = {}
        self._lock = Lock()

    def create(self, transcript: CallTranscript) -> CallTranscript:
        with self._lock:
            if transcript.transcript_id in self._transcripts or self.get_by_interaction(
                transcript.interaction_id
            ):
                raise ValueError("Transcript already exists.")
            self._transcripts[transcript.transcript_id] = transcript
        return transcript

    def get_by_interaction(self, interaction_id: str) -> CallTranscript | None:
        return next(
            (item for item in self._transcripts.values() if item.interaction_id == interaction_id),
            None,
        )

    def update(self, transcript: CallTranscript) -> CallTranscript:
        with self._lock:
            if transcript.transcript_id not in self._transcripts:
                raise ValueError("Transcript does not exist.")
            self._transcripts[transcript.transcript_id] = transcript
        return transcript


class InMemorySatisfactionSurveyRepository:
    def __init__(self) -> None:
        self._surveys: dict[str, SatisfactionSurvey] = {}
        self._lock = Lock()

    def create(self, survey: SatisfactionSurvey) -> SatisfactionSurvey:
        with self._lock:
            if survey.survey_id in self._surveys or (
                survey.interaction_id and self.get_by_interaction(survey.interaction_id)
            ):
                raise ValueError("Satisfaction survey already exists.")
            self._surveys[survey.survey_id] = survey
        return survey

    def get_by_interaction(self, interaction_id: str) -> SatisfactionSurvey | None:
        return next(
            (item for item in self._surveys.values() if item.interaction_id == interaction_id),
            None,
        )

    def list_by_agent(self, agent_id: str) -> list[SatisfactionSurvey]:
        return [item for item in self._surveys.values() if item.agent_id == agent_id]


class InMemoryCardPurchaseRepository:
    """Joins the in-memory transactions with their card products, like the SQL version."""

    def __init__(
        self,
        transactions: InMemoryTransactionRepository,
        products: InMemoryProductRepository,
        *,
        source: str = "postgres",
    ) -> None:
        self.transactions = transactions
        self.products = products
        self.source = source

    def _card_purchase(self, transaction: Transaction) -> CardTransaction | None:
        product = self.products.get_by_id(transaction.product_id)
        if (
            product is None
            or product.customer_id != transaction.customer_id
            or product.product_type not in CARD_PRODUCT_TYPES
            or transaction.transaction_type != CARD_PURCHASE_TYPE
        ):
            return None
        return CardTransaction(
            transaction=transaction,
            card_type=product.product_type,
            card_last_four=product.product_number[-4:],
            card_status=product.product_status,
            source=self.source,
        )

    def list_by_customer(self, customer_id: str, *, limit: int = 500) -> list[CardTransaction]:
        purchases = [
            purchase
            for transaction in self.transactions.list_by_customer(customer_id)
            if (purchase := self._card_purchase(transaction)) is not None
        ]
        return purchases[:limit]

    def get_for_customer(self, customer_id: str, transaction_id: str) -> CardTransaction | None:
        transaction = self.transactions.get_by_id(transaction_id)
        if transaction is None or transaction.customer_id != customer_id:
            return None
        return self._card_purchase(transaction)


class InMemoryAccountRegistrationRepository:
    """Test double for the transactional PostgreSQL account replacement."""

    def __init__(
        self,
        *,
        customers: InMemoryCustomerRepository,
        products: InMemoryProductRepository,
        transactions: InMemoryTransactionRepository,
        complaints: InMemoryComplaintRepository,
        sessions: InMemorySessionRepository,
        interactions: InMemoryCallCenterInteractionRepository,
        transcripts: InMemoryCallTranscriptRepository,
        surveys: InMemorySatisfactionSurveyRepository,
    ) -> None:
        self.customers = customers
        self.products = products
        self.transactions = transactions
        self.complaints = complaints
        self.sessions = sessions
        self.interactions = interactions
        self.transcripts = transcripts
        self.surveys = surveys
        self._lock = Lock()

    @staticmethod
    def _remove_customer_items(items: dict[str, Any], customer_id: str) -> None:
        for key, item in tuple(items.items()):
            if item.customer_id == customer_id:
                del items[key]

    def register(self, customer: Customer, product: Product) -> tuple[Customer, Product]:
        with self._lock:
            document_owner = self.customers.get_by_document(customer.document_number)
            phone_owner = (
                self.customers.get_by_phone(customer.mobile_phone)
                if customer.mobile_phone
                else None
            )
            if document_owner is not None and document_owner != phone_owner:
                raise ValueError("FACTORED_ID already exists.")

            if phone_owner is not None:
                customer_id = phone_owner.customer_id
                self._remove_customer_items(self.surveys._surveys, customer_id)
                self._remove_customer_items(self.transcripts._transcripts, customer_id)
                self._remove_customer_items(self.interactions._interactions, customer_id)
                self._remove_customer_items(self.complaints._complaints, customer_id)
                self._remove_customer_items(self.transactions._transactions, customer_id)
                self._remove_customer_items(self.products._products, customer_id)
                self._remove_customer_items(self.sessions._sessions, customer_id)
                del self.customers._customers[customer_id]

            self.customers._customers[customer.customer_id] = customer
            self.products._products[product.product_id] = product
        return customer, product


def new_repositories() -> Repositories:
    customers = InMemoryCustomerRepository()
    products = InMemoryProductRepository()
    transactions = InMemoryTransactionRepository()
    complaints = InMemoryComplaintRepository()
    sessions = InMemorySessionRepository()
    interactions = InMemoryCallCenterInteractionRepository()
    transcripts = InMemoryCallTranscriptRepository()
    surveys = InMemorySatisfactionSurveyRepository()
    return Repositories(
        customers=customers,
        products=products,
        account_registration=InMemoryAccountRegistrationRepository(
            customers=customers,
            products=products,
            transactions=transactions,
            complaints=complaints,
            sessions=sessions,
            interactions=interactions,
            transcripts=transcripts,
            surveys=surveys,
        ),
        transactions=transactions,
        complaints=complaints,
        sessions=sessions,
        service_agents=InMemoryServiceAgentRepository(),
        call_center_interactions=interactions,
        call_transcripts=transcripts,
        satisfaction_surveys=surveys,
        card_purchases=InMemoryCardPurchaseRepository(transactions, products),
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
    repositories.service_agents._agents.clear()
    repositories.call_center_interactions._interactions.clear()
    repositories.call_transcripts._transcripts.clear()
    repositories.satisfaction_surveys._surveys.clear()


# ----------------------------------------------------------------------------- synthetic data

DEMO_CUSTOMERS = (
    {
        "customer_id": "DEMO-BR-GABRIEL-123456",
        "document_number": "123456",
        "first_name": "Gabriel",
        "last_name": "Silveira",
        "country": "Brazil",
        "city": "São Paulo",
        "state": "SP",
        "accent": Accent.PORTUGUESE,
        "phone": "+5511981020050",
        "date_of_birth": date(1999, 1, 1),
        "gender": Gender.MALE,
    },
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
                    date_of_birth=data.get("date_of_birth", date(1990, 1, 1)),
                    gender=data.get("gender", Gender.PREFER_NOT_TO_SAY),
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
            seed_demo_card(products, data["customer_id"])


DEMO_CARD_NUMBER = "9999999999999999"


def demo_card_product_id(customer_id: str) -> str:
    return f"DEMO-CARD-9999-{customer_id}"


def seed_demo_card(products: ProductRepository, customer_id: str) -> Product:
    """Create or return the customer's synthetic credit card ending in 9999."""

    existing = products.get_by_id(demo_card_product_id(customer_id))
    if existing is not None:
        return existing
    now = datetime.now(UTC)
    return products.create(
        Product(
            product_id=demo_card_product_id(customer_id),
            customer_id=customer_id,
            product_type="Credit Card",
            product_number=DEMO_CARD_NUMBER,
            currency="USD",
            current_balance=0.0,
            credit_limit=10_000.0,
            opening_date=now.date(),
            opening_branch_id=1,
            product_status="Active",
            opening_channel="Demo",
            has_linked_app=True,
            last_updated=now,
        )
    )


def demo_fruit_transactions(customer_id: str, location_seed: int = 19) -> tuple[Transaction, ...]:
    """Ten deterministic card purchases on the customer's demo card, with varied locations."""

    locations = [
        ("Argentina", "Buenos Aires", -34.6037, -58.3816),
        ("Brazil", "São Paulo", -23.5505, -46.6333),
        ("Chile", "Santiago", -33.4489, -70.6693),
        ("Colombia", "Bogotá", 4.7110, -74.0721),
        ("Costa Rica", "San José", 9.9281, -84.0907),
        ("Mexico", "Mexico City", 19.4326, -99.1332),
        ("Peru", "Lima", -12.0464, -77.0428),
        ("Portugal", "Lisbon", 38.7223, -9.1393),
        ("Spain", "Madrid", 40.4168, -3.7038),
        ("United States", "Miami", 25.7617, -80.1918),
    ]
    selected_locations = random.Random(location_seed).sample(locations, k=len(locations))
    fruits = (
        ("lemon", "Lemon Drop Market", 12.49),
        ("strawberry", "Strawberry Fields Shop", 18.95),
        ("coconut", "Coconut Island Grocer", 27.80),
        ("passion-fruit", "Passion Fruit Pantry", 34.25),
        ("banana", "Banana Bunch Market", 41.60),
        ("apple", "Apple Orchard Store", 56.90),
        ("papaya", "Papaya Sunrise Market", 63.40),
        ("peach", "Peach Grove Grocer", 78.15),
        ("grapes", "Grapes and Vine Market", 92.75),
        ("mango", "Mango Gold Store", 125.30),
    )
    anchor = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)
    transactions: list[Transaction] = []
    for index, ((fruit, merchant, amount), location) in enumerate(
        zip(fruits, selected_locations, strict=True), start=1
    ):
        country, city, latitude, longitude = location
        transaction_time = anchor + timedelta(days=index - 1, hours=index)
        transactions.append(
            Transaction(
                transaction_id=f"FRUIT-{index:02d}-{fruit.upper()}",
                transaction_date=transaction_time,
                process_date=transaction_time.date(),
                product_id=demo_card_product_id(customer_id),
                customer_id=customer_id,
                transaction_type="Purchase",
                transaction_category="Fruit purchase",
                amount=amount,
                currency="USD",
                amount_usd=amount,
                channel="E-commerce" if index % 2 else "POS",
                branch_id=None,
                merchant_name=merchant,
                merchant_category="Fruit and produce",
                transaction_country=country,
                transaction_city=city,
                transaction_status="Approved",
                response_code="00",
                is_fraud=False,
                fraud_score=round(0.01 * index, 2),
                latitude=latitude,
                longitude=longitude,
            )
        )
    return tuple(transactions)


def fruit_search_repository(customer_id: str):
    """SQLite transaction search over `demo_fruit_transactions` for one customer."""

    from dispute_agent.transaction_search import SQLiteTransactionSearchRepository

    return SQLiteTransactionSearchRepository(transactions=demo_fruit_transactions(customer_id))


def voice_repositories(customer_id: str = "CLI-002", **overrides: Any) -> dict[str, Any]:
    """Keyword arguments for `VoiceCallService` / `SipRealtimeGateway` backed by fresh doubles.

    The customer owns the demo card that the fruit transactions were charged to.
    """

    fresh = new_repositories()
    seed_demo_card(fresh.products, customer_id)
    values: dict[str, Any] = {
        "transaction_repository": fruit_search_repository(customer_id),
        "product_repository": fresh.products,
        "complaint_repository": fresh.complaints,
        "service_agent_repository": fresh.service_agents,
        "interaction_repository": fresh.call_center_interactions,
        "transcript_repository": fresh.call_transcripts,
        "satisfaction_survey_repository": fresh.satisfaction_surveys,
    }
    values.update({key: value for key, value in overrides.items() if value is not None})
    return values


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
