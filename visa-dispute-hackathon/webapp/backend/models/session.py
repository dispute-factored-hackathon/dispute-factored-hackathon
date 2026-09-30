from datetime import datetime

from pydantic import BaseModel


class CustomerSession(BaseModel):
    session_id: str
    customer_id: str

    created_at: datetime
    expires_at: datetime
