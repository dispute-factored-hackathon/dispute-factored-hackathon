import secrets
from datetime import UTC, datetime

from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.repositories.interfaces import (
    CustomerRepository,
    ProductRepository,
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
    ) -> None:
        self.customers = customers
        self.products = products

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

    @staticmethod
    def _generate_card_number() -> str:
        return "".join(str(secrets.randbelow(10)) for _ in range(16))
