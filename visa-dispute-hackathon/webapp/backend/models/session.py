from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class AuthenticationMethod(StrEnum):
    FACTORED_ID = "factored_id"
    DEMO_SELECTOR = "demo_selector"


class CustomerSession(BaseModel):
    session_id: str
    customer_id: str
    authentication_method: AuthenticationMethod

    created_at: datetime
    expires_at: datetime
