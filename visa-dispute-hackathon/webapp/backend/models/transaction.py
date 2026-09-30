from datetime import date, datetime

from pydantic import BaseModel


class Transaction(BaseModel):
    transaction_id: str

    transaction_date: datetime
    process_date: date

    product_id: str
    customer_id: str

    transaction_type: str
    transaction_category: str | None

    amount: float
    currency: str
    amount_usd: float | None

    channel: str

    branch_id: str | None = None

    merchant_name: str | None
    merchant_category: str | None

    transaction_country: str
    transaction_city: str | None

    transaction_status: str
    response_code: str | None = None

    is_fraud: bool
    fraud_score: float | None = None

    latitude: float | None = None
    longitude: float | None = None
