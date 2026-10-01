from webapp.backend.models.product import Product
from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.interfaces import (
    ProductRepository,
    TransactionRepository,
)


class TransactionNotFoundError(Exception):
    pass


class TransactionAccessDeniedError(Exception):
    pass


class TransactionService:
    def __init__(
        self,
        transactions: TransactionRepository,
        products: ProductRepository,
    ) -> None:
        self.transactions = transactions
        self.products = products

    def list_customer_transactions(
        self,
        customer_id: str,
    ) -> list[Transaction]:
        return self.transactions.list_by_customer(customer_id)

    def get_customer_transaction(
        self,
        transaction_id: str,
        customer_id: str,
    ) -> Transaction:
        transaction = self.transactions.get_by_id(transaction_id)

        if transaction is None:
            raise TransactionNotFoundError

        if transaction.customer_id != customer_id:
            raise TransactionAccessDeniedError

        return transaction

    def get_product(
        self,
        product_id: str,
    ) -> Product | None:
        return self.products.get_by_id(product_id)
