from datetime import UTC, datetime

from webapp.backend.models.product import Product
from webapp.backend.repositories.interfaces import (
    ProductRepository,
)


class ProductNotFoundError(Exception):
    pass


class ProductAccessDeniedError(Exception):
    pass


class ProductService:
    def __init__(
        self,
        products: ProductRepository,
    ) -> None:
        self.products = products

    def list_customer_products(
        self,
        customer_id: str,
    ) -> list[Product]:
        return self.products.list_by_customer(customer_id)

    def block(
        self,
        product_id: str,
        customer_id: str,
    ) -> Product:
        product = self._owned_product(
            product_id,
            customer_id,
        )

        if product.product_status == "Blocked":
            return product

        updated = product.model_copy(
            update={
                "product_status": "Blocked",
                "last_updated": datetime.now(UTC),
            }
        )

        return self.products.update(updated)

    def unblock(
        self,
        product_id: str,
        customer_id: str,
    ) -> Product:
        product = self._owned_product(
            product_id,
            customer_id,
        )

        if product.product_status == "Active":
            return product

        updated = product.model_copy(
            update={
                "product_status": "Active",
                "last_updated": datetime.now(UTC),
            }
        )

        return self.products.update(updated)

    def _owned_product(
        self,
        product_id: str,
        customer_id: str,
    ) -> Product:
        product = self.products.get_by_id(product_id)

        if product is None:
            raise ProductNotFoundError

        if product.customer_id != customer_id:
            raise ProductAccessDeniedError

        return product
