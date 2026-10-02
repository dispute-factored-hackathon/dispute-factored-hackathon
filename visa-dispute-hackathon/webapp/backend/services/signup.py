import secrets
from datetime import UTC, datetime, timedelta

from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.interfaces import (
    ComplaintRepository,
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
        complaints: ComplaintRepository,
    ) -> None:
        self.customers = customers
        self.products = products
        self.transactions = transactions
        self.complaints = complaints

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
            preferred_locale=request.preferred_locale,
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

        self._create_demo_complaints(
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
            preferred_locale=customer.interface_locale,
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

    def _create_demo_complaints(
        self,
        *,
        customer: Customer,
        product: Product,
        now: datetime,
    ) -> None:
        resolved_creation = now - timedelta(days=45)

        resolved_complaint = Complaint(
            complaint_id=("CMP-DEMO-" + secrets.token_hex(6).upper()),
            creation_date=resolved_creation,
            process_date=resolved_creation.date(),
            customer_id=customer.customer_id,
            case_type="Claim",
            category="Card Purchase",
            subcategory="Duplicate Charge",
            reception_channel="Web",
            affected_product_id=product.product_id,
            related_branch_id=None,
            origin_interaction_id=None,
            description=("Customer reported a duplicate charge from Factored Coffee."),
            claimed_amount=8.75,
            currency="USD",
            priority="Medium",
            status="Resolved",
            assigned_agent_id="IZZY",
            assignment_date=(resolved_creation + timedelta(hours=1)),
            first_response_date=(resolved_creation + timedelta(hours=2)),
            resolution_date=(resolved_creation + timedelta(days=2)),
            closing_date=(resolved_creation + timedelta(days=3)),
            sla_breached=False,
            resolution_days=2,
            resolution=("Duplicate charge confirmed. The disputed amount was refunded."),
            compensation_granted=8.75,
            resolution_satisfaction=5.0,
            is_repeat_complainer=False,
        )

        open_creation = now - timedelta(days=4)

        open_complaint = Complaint(
            complaint_id=("CMP-DEMO-" + secrets.token_hex(6).upper()),
            creation_date=open_creation,
            process_date=open_creation.date(),
            customer_id=customer.customer_id,
            case_type="Claim",
            category="Card Purchase",
            subcategory="Unrecognized Transaction",
            reception_channel="Call Center",
            affected_product_id=product.product_id,
            related_branch_id=None,
            origin_interaction_id=None,
            description=("Customer reported an unrecognized online purchase and requested review."),
            claimed_amount=129.90,
            currency="USD",
            priority="High",
            status="In Review",
            assigned_agent_id="IZZY",
            assignment_date=(open_creation + timedelta(minutes=10)),
            first_response_date=(open_creation + timedelta(minutes=15)),
            resolution_date=None,
            closing_date=None,
            sla_breached=False,
            resolution_days=None,
            resolution=None,
            compensation_granted=None,
            resolution_satisfaction=None,
            is_repeat_complainer=True,
        )

        self.complaints.create(resolved_complaint)

        self.complaints.create(open_complaint)

    @staticmethod
    def _generate_card_number() -> str:
        return "".join(str(secrets.randbelow(10)) for _ in range(16))
