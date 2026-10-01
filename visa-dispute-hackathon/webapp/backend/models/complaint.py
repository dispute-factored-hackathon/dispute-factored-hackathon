from datetime import date, datetime

from pydantic import BaseModel


class Complaint(BaseModel):
    complaint_id: str

    creation_date: datetime
    process_date: date

    customer_id: str

    case_type: str
    category: str
    subcategory: str | None

    reception_channel: str

    affected_product_id: str | None = None
    related_branch_id: str | None = None
    origin_interaction_id: str | None = None

    description: str

    claimed_amount: float
    currency: str

    priority: str
    status: str

    assigned_agent_id: str | None = None

    assignment_date: datetime | None = None
    first_response_date: datetime | None = None
    resolution_date: datetime | None = None
    closing_date: datetime | None = None

    sla_breached: bool = False
    resolution_days: int | None = None

    resolution: str | None = None
    compensation_granted: float | None = None
    resolution_satisfaction: float | None = None

    is_repeat_complainer: bool = False
