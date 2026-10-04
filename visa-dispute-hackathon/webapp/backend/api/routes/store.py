from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from webapp.backend.api.dependencies import RepositoriesDependency, require_customer
from webapp.backend.models.customer import Customer
from webapp.backend.models.store import StoreCartItem, StoreProduct
from webapp.backend.repositories.store_catalog import StaticStoreCatalogRepository
from webapp.backend.schemas.store import (
    CheckoutRequest,
    CheckoutResponse,
    StoreProductResponse,
)
from webapp.backend.services.store import (
    CheckoutValidationError,
    StoreProductNotFoundError,
    StoreService,
)
from webapp.backend.store_catalog import STORE_PRODUCTS

router = APIRouter(prefix="/api/store", tags=["shady-business"])

store_catalog = StaticStoreCatalogRepository(STORE_PRODUCTS)


def get_store_service(repositories: RepositoriesDependency) -> StoreService:
    return StoreService(store_catalog, repositories.products, repositories.transactions)


StoreServiceDependency = Annotated[StoreService, Depends(get_store_service)]


def product_response(product: StoreProduct) -> StoreProductResponse:
    return StoreProductResponse(**product.model_dump())


@router.get("/products", response_model=list[StoreProductResponse])
def list_store_products(store_service: StoreServiceDependency) -> list[StoreProductResponse]:
    return [product_response(product) for product in store_service.list_catalog()]


@router.get("/products/{product_id}", response_model=StoreProductResponse)
def get_store_product(
    product_id: str, store_service: StoreServiceDependency
) -> StoreProductResponse:
    try:
        return product_response(store_service.get_catalog_product(product_id))
    except StoreProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shady product not found.",
        ) from error


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(
    request: CheckoutRequest,
    customer: Annotated[Customer, Depends(require_customer)],
    store_service: StoreServiceDependency,
) -> CheckoutResponse:
    try:
        purchase, _anomaly, item_count = store_service.checkout(
            customer_id=customer.customer_id,
            card_product_id=request.card_product_id,
            items=[StoreCartItem(**item.model_dump()) for item in request.items],
        )
    except StoreProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Your cart contains a product that is no longer available.",
        ) from error
    except CheckoutValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return CheckoutResponse(
        order_id=f"ORDER-{purchase.transaction_id.removeprefix('TRX-SHADY-')}",
        transaction_id=purchase.transaction_id,
        item_count=item_count,
        total=purchase.amount,
        currency=purchase.currency,
        message=(
            "Your simulated order is confirmed. Review your bank activity to see how the "
            "mock payment processor recorded it."
        ),
    )
