from datetime import datetime

from pydantic import BaseModel


class ComplaintListItemResponse(BaseModel):
    complaint_id: str
    creation_date: datetime

    case_type: str
    category: str
    subcategory: str | None

    claimed_amount: float
    currency: str

    status: str
    priority: str


class ComplaintDetailResponse(BaseModel):
    complaint_id: str

    creation_date: datetime

    case_type: str
    category: str
    subcategory: str | None

    reception_channel: str

    affected_product_id: str | None

    description: str

    claimed_amount: float
    currency: str

    priority: str
    status: str

    assignment_date: datetime | None
    first_response_date: datetime | None

    resolution_date: datetime | None
    closing_date: datetime | None

    sla_breached: bool
    resolution_days: int | None

    resolution: str | None
    compensation_granted: float | None
    resolution_satisfaction: float | None
