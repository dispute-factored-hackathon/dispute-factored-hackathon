from webapp.backend.models.store import StoreProduct


class StaticStoreCatalogRepository:
    """Read-only catalog of the parody shop; it is product copy, not customer data."""

    def __init__(self, products: tuple[StoreProduct, ...]) -> None:
        self._products = {product.product_id: product for product in products}

    def list_all(self) -> list[StoreProduct]:
        return list(self._products.values())

    def get_by_id(self, product_id: str) -> StoreProduct | None:
        return self._products.get(product_id)
