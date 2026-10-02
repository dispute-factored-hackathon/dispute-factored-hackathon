"""Shared mock-card identity for demo channels."""

from datetime import UTC, datetime

from webapp.backend.models.product import Product
from webapp.backend.repositories.interfaces import ProductRepository

DEMO_CARD_NUMBER = "9999999999999999"


def demo_card_product_id(customer_id: str) -> str:
    """Keep the mock product stable while preserving customer ownership."""
    return f"DEMO-CARD-9999-{customer_id}"


def seed_demo_card(products: ProductRepository, customer_id: str) -> Product:
    """Create or return the customer's replaceable mock credit card."""
    product_id = demo_card_product_id(customer_id)
    existing = products.get_by_id(product_id)
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    return products.create(
        Product(
            product_id=product_id,
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
