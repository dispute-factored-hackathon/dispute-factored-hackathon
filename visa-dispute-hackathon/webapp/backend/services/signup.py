import secrets
from datetime import UTC, datetime, timedelta

from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.interfaces import (
    CustomerRepository,
    ProductRepository,
    TransactionRepository,
)
from webapp.backend.schemas.customer import (
    CustomerSignupRequest,
    CustomerSignupResponse,
    DemoCardResponse,
)


class SignupService:
    def __init__(
        self,
        customers: CustomerRepository,
        products: ProductRepository,
        transactions: TransactionRepository,
    ) -> None:
        self.customers = customers
        self.products = products
        self.transactions = transactions

    def signup(
        self,
        request: CustomerSignupRequest,
    ) -> CustomerSignupResponse:
        if self.customers.get_by_document(request.factored_id):
            raise ValueError("FACTORED_ID already exists.")

        if request.mobile_phone and self.customers.get_by_phone(request.mobile_phone):
            raise ValueError("Phone number already exists.")

        now = datetime.now(UTC)

        customer_id = f"CLI-DEMO-{secrets.token_hex(6).upper()}"

        customer = Customer(
            customer_id=customer_id,
            document_number=request.factored_id,
            document_type="FACTORED_ID",
            first_name=request.first_name,
            last_name=request.last_name,
            date_of_birth=request.date_of_birth,
            gender=request.gender,
            mobile_phone=request.mobile_phone,
            city="Factored Village",
            state="Factored Fields",
            country="Factoredland",
            detected_accent=request.preferred_accent,
            segment="Factored",
            registration_date=now,
            registration_branch_id=1,
            customer_status="Active",
            last_updated=now,
        )

        self.customers.create(customer)

        card_number = self._generate_card_number()

        product = Product(
            product_id=(f"PRD-DEMO-{secrets.token_hex(6).upper()}"),
            customer_id=customer.customer_id,
            product_type="Credit Card",
            product_number=card_number,
            currency="USD",
            current_balance=0.0,
            credit_limit=999_999_999.0,
            opening_date=now.date(),
            opening_branch_id=1,
            product_status="Active",
            opening_channel="Web",
            has_linked_app=True,
            last_updated=now,
        )

        self.products.create(product)

        self._create_demo_transactions(
            customer=customer,
            product=product,
            now=now,
        )

        return CustomerSignupResponse(
            customer_id=customer.customer_id,
            first_name=customer.first_name,
            last_name=customer.last_name,
            factored_id=customer.document_number,
            mobile_phone=customer.mobile_phone,
            preferred_accent=customer.detected_accent,
            customer_status=customer.customer_status,
            demo_card=DemoCardResponse(
                product_id=product.product_id,
                last_four=product.product_number[-4:],
                product_type=product.product_type,
                currency=product.currency,
                product_status=product.product_status,
            ),
        )

    def _create_demo_transactions(
        self,
        *,
        customer: Customer,
        product: Product,
        now: datetime,
    ) -> None:
        demo_transactions = (
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

        for data in demo_transactions:
            transaction_date = now - timedelta(days=data["days_ago"])

            transaction = Transaction(
                transaction_id=("TRX-DEMO-" + secrets.token_hex(6).upper()),
                transaction_date=transaction_date,
                process_date=transaction_date.date(),
                product_id=product.product_id,
                customer_id=customer.customer_id,
                transaction_type="Purchase",
                transaction_category=(data["transaction_category"]),
                amount=data["amount"],
                currency="USD",
                amount_usd=data["amount"],
                channel=data["channel"],
                branch_id=None,
                merchant_name=data["merchant_name"],
                merchant_category=(data["merchant_category"]),
                transaction_country=data["country"],
                transaction_city=data["city"],
                transaction_status="Approved",
                response_code="00",
                is_fraud=data["is_fraud"],
                fraud_score=data["fraud_score"],
                latitude=None,
                longitude=None,
            )

            self.transactions.create(transaction)

    @staticmethod
    def _generate_card_number() -> str:
        return "".join(str(secrets.randbelow(10)) for _ in range(16))
