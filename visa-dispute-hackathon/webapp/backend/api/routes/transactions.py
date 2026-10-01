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
from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.mock import (
    product_repository,
    transaction_repository,
)
from webapp.backend.schemas.transaction import (
    TransactionDetailResponse,
    TransactionListItemResponse,
)
from webapp.backend.services.transactions import (
    TransactionAccessDeniedError,
    TransactionNotFoundError,
    TransactionService,
)

router = APIRouter(
    prefix="/api/transactions",
    tags=["transactions"],
)


transaction_service = TransactionService(
    transaction_repository,
    product_repository,
)


def card_last_four(
    transaction: Transaction,
) -> str:
    product = transaction_service.get_product(transaction.product_id)

    if product is None:
        return "----"

    return product.product_number[-4:]


def list_response(
    transaction: Transaction,
) -> TransactionListItemResponse:
    return TransactionListItemResponse(
        transaction_id=(transaction.transaction_id),
        transaction_date=(transaction.transaction_date),
        product_id=transaction.product_id,
        card_last_four=card_last_four(transaction),
        merchant_name=(transaction.merchant_name),
        transaction_category=(transaction.transaction_category),
        amount=transaction.amount,
        currency=transaction.currency,
        channel=transaction.channel,
        transaction_status=(transaction.transaction_status),
        is_fraud=transaction.is_fraud,
    )


def detail_response(
    transaction: Transaction,
) -> TransactionDetailResponse:
    return TransactionDetailResponse(
        transaction_id=(transaction.transaction_id),
        transaction_date=(transaction.transaction_date),
        product_id=transaction.product_id,
        card_last_four=card_last_four(transaction),
        transaction_type=(transaction.transaction_type),
        transaction_category=(transaction.transaction_category),
        amount=transaction.amount,
        currency=transaction.currency,
        channel=transaction.channel,
        merchant_name=(transaction.merchant_name),
        merchant_category=(transaction.merchant_category),
        transaction_country=(transaction.transaction_country),
        transaction_city=(transaction.transaction_city),
        transaction_status=(transaction.transaction_status),
        is_fraud=transaction.is_fraud,
        fraud_score=transaction.fraud_score,
    )


@router.get(
    "",
    response_model=list[TransactionListItemResponse],
)
def list_transactions(
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
) -> list[TransactionListItemResponse]:
    transactions = transaction_service.list_customer_transactions(customer.customer_id)

    return [list_response(transaction) for transaction in transactions]


@router.get(
    "/{transaction_id}",
    response_model=TransactionDetailResponse,
)
def get_transaction(
    transaction_id: str,
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
) -> TransactionDetailResponse:
    try:
        transaction = transaction_service.get_customer_transaction(
            transaction_id,
            customer.customer_id,
        )

    except (
        TransactionNotFoundError,
        TransactionAccessDeniedError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found.",
        ) from error

    return detail_response(transaction)
