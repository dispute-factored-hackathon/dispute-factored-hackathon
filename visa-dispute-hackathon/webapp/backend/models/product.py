from datetime import date, datetime

from pydantic import BaseModel


class Product(BaseModel):
    product_id: str
    customer_id: str

    product_type: str
    product_number: str

    currency: str

    current_balance: float
    credit_limit: float

    opening_date: date
    opening_branch_id: int

    product_status: str
    opening_channel: str
    has_linked_app: bool

    last_updated: datetime
