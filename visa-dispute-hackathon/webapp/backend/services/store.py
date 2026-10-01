import random
import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol

from webapp.backend.models.product import Product
from webapp.backend.models.store import StoreCartItem, StoreProduct
from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.interfaces import (
    ProductRepository,
    StoreCatalogRepository,
    TransactionRepository,
)

SOUTH_ASIAN_LOCATIONS = (
    ("Bangladesh", "Dhaka"),
    ("Bhutan", "Thimphu"),
    ("India", "Mumbai"),
    ("Maldives", "Malé"),
    ("Nepal", "Kathmandu"),
    ("Pakistan", "Karachi"),
    ("Sri Lanka", "Colombo"),
)


class StoreProductNotFoundError(Exception):
    pass


class CheckoutValidationError(Exception):
    pass


class AnomalyStrategy(Protocol):
    def build(self, purchase: Transaction) -> Transaction: ...


class RandomAnomalyStrategy:
    def __init__(self, generator: random.Random | random.SystemRandom | None = None) -> None:
        self.generator = generator or random.SystemRandom()

    def build(self, purchase: Transaction) -> Transaction:
        if self.generator.choice(("duplicate", "foreign_fraud")) == "duplicate":
            return purchase.model_copy(
                update={
                    "transaction_id": f"TRX-SHADY-{secrets.token_hex(6).upper()}",
                    "transaction_date": purchase.transaction_date + timedelta(seconds=1),
                    "transaction_category": "Duplicate card charge",
                    "fraud_score": 0.18,
                }
            )

        country, city = self.generator.choice(SOUTH_ASIAN_LOCATIONS)
        amount = float(self.generator.randrange(90000, 250001) / 100)
        return purchase.model_copy(
            update={
                "transaction_id": f"TRX-SHADY-{secrets.token_hex(6).upper()}",
                "transaction_date": purchase.transaction_date + timedelta(seconds=1),
                "transaction_category": "Unrecognized luxury electronics",
                "amount": amount,
                "amount_usd": amount,
                "merchant_name": "Royal Bengal Electronics Export",
                "merchant_category": "Electronics",
                "transaction_country": country,
                "transaction_city": city,
                "is_fraud": True,
                "fraud_score": 0.97,
            }
        )


class StoreService:
    def __init__(
        self,
        catalog: StoreCatalogRepository,
        products: ProductRepository,
        transactions: TransactionRepository,
        anomaly_strategy: AnomalyStrategy | None = None,
    ) -> None:
        self.catalog = catalog
        self.products = products
        self.transactions = transactions
        self.anomaly_strategy = anomaly_strategy or RandomAnomalyStrategy()

    def list_catalog(self) -> list[StoreProduct]:
        return self.catalog.list_all()

    def get_catalog_product(self, product_id: str) -> StoreProduct:
        product = self.catalog.get_by_id(product_id)
        if product is None:
            raise StoreProductNotFoundError
        return product

    def checkout(
        self,
        *,
        customer_id: str,
        card_product_id: str,
        items: list[StoreCartItem],
    ) -> tuple[Transaction, Transaction, int]:
        card = self._validate_card(card_product_id, customer_id)
        quantities = self._validate_items(items)
        item_count = sum(quantities.values())
        total = round(
            sum(
                self.get_catalog_product(product_id).price * quantity
                for product_id, quantity in quantities.items()
            ),
            2,
        )
        purchase = self._purchase_transaction(card, customer_id, total)
        anomaly = self.anomaly_strategy.build(purchase)
        self.transactions.create(purchase)
        self.transactions.create(anomaly)
        return purchase, anomaly, item_count

    def _validate_card(self, product_id: str, customer_id: str) -> Product:
        product = self.products.get_by_id(product_id)
        if product is None or product.customer_id != customer_id:
            raise CheckoutValidationError("Choose one of your own demo credit cards.")
        if "card" not in product.product_type.casefold():
            raise CheckoutValidationError("Only a demo credit card can be used at checkout.")
        if product.product_status != "Active":
            raise CheckoutValidationError(
                "This card is blocked or inactive. Choose an active card."
            )
        return product

    def _validate_items(self, items: list[StoreCartItem]) -> dict[str, int]:
        quantities: dict[str, int] = {}
        for item in items:
            self.get_catalog_product(item.product_id)
            quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
            if quantities[item.product_id] > 10:
                raise CheckoutValidationError("A product quantity cannot exceed 10.")
        if not quantities:
            raise CheckoutValidationError("Your cart is empty.")
        return quantities

    @staticmethod
    def _purchase_transaction(card: Product, customer_id: str, total: float) -> Transaction:
        now = datetime.now(UTC)
        return Transaction(
            transaction_id=f"TRX-SHADY-{secrets.token_hex(6).upper()}",
            transaction_date=now,
            process_date=now.date(),
            product_id=card.product_id,
            customer_id=customer_id,
            transaction_type="Purchase",
            transaction_category="Novelty retail",
            amount=total,
            currency="USD",
            amount_usd=total,
            channel="Web",
            branch_id=None,
            merchant_name="Shady Business",
            merchant_category="Novelty Retail",
            transaction_country="Factoredland",
            transaction_city="Factored Village",
            transaction_status="Approved",
            response_code="00",
            is_fraud=False,
            fraud_score=0.07,
            latitude=None,
            longitude=None,
        )
