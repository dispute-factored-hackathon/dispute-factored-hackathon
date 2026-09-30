from datetime import datetime

from pydantic import BaseModel


class TransactionListItemResponse(BaseModel):
    transaction_id: str
    transaction_date: datetime

    product_id: str
    card_last_four: str

    merchant_name: str | None
    transaction_category: str | None

    amount: float
    currency: str

    channel: str
    transaction_status: str

    is_fraud: bool


class TransactionDetailResponse(BaseModel):
    transaction_id: str
    transaction_date: datetime

    product_id: str
    card_last_four: str

    transaction_type: str
    transaction_category: str | None

    amount: float
    currency: str

    channel: str

    merchant_name: str | None
    merchant_category: str | None

    transaction_country: str
    transaction_city: str | None

    transaction_status: str

    is_fraud: bool
    fraud_score: float | None
