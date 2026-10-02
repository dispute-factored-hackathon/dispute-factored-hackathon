from datetime import date

from pydantic import BaseModel


class ServiceAgent(BaseModel):
    agent_id: str
    employee_code: str
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    native_accent: str
    country_of_origin: str
    assigned_branch_id: str | None = None
    agent_type: str
    experience_level: str
    languages: str
    specialty: str | None = None
    hire_date: date
    avg_csat: float | None = None
    total_monthly_interactions: int | None = None
    agent_status: str
    work_shift: str
