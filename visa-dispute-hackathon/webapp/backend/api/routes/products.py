from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from webapp.backend.api.dependencies import (
    require_customer,
)
from webapp.backend.models.customer import Customer
from webapp.backend.models.product import Product
from webapp.backend.repositories.mock import (
    product_repository,
)
from webapp.backend.schemas.product import (
    ProductResponse,
    ProductStatusResponse,
)
from webapp.backend.services.products import (
    ProductAccessDeniedError,
    ProductNotFoundError,
    ProductService,
)

router = APIRouter(
    prefix="/api/products",
    tags=["products"],
)


product_service = ProductService(
    product_repository,
)


def masked_number(
    product_number: str,
) -> str:
    last_four = product_number[-4:]

    return f"•••• •••• •••• {last_four}"


def product_response(
    product: Product,
) -> ProductResponse:
    return ProductResponse(
        product_id=product.product_id,
        product_type=product.product_type,
        masked_number=masked_number(product.product_number),
        last_four=product.product_number[-4:],
        currency=product.currency,
        product_status=product.product_status,
    )


@router.get(
    "",
    response_model=list[ProductResponse],
)
def list_products(
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
) -> list[ProductResponse]:
    products = product_service.list_customer_products(customer.customer_id)

    return [product_response(product) for product in products]


@router.post(
    "/{product_id}/block",
    response_model=ProductStatusResponse,
)
def block_product(
    product_id: str,
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
) -> ProductStatusResponse:
    try:
        product = product_service.block(
            product_id,
            customer.customer_id,
        )

    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found.",
        ) from error

    except ProductAccessDeniedError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found.",
        ) from error

    return ProductStatusResponse(
        product_id=product.product_id,
        product_status=product.product_status,
    )


@router.post(
    "/{product_id}/unblock",
    response_model=ProductStatusResponse,
)
def unblock_product(
    product_id: str,
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
) -> ProductStatusResponse:
    try:
        product = product_service.unblock(
            product_id,
            customer.customer_id,
        )

    except ProductNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found.",
        ) from error

    except ProductAccessDeniedError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found.",
        ) from error

    return ProductStatusResponse(
        product_id=product.product_id,
        product_status=product.product_status,
    )
