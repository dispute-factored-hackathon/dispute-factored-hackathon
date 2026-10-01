from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class Accent(StrEnum):
    ENGLISH = "english"
    PORTUGUESE = "portuguese"
    MEXICAN_SPANISH = "mexican_spanish"
    COLOMBIAN_SPANISH = "colombian_spanish"
    ARGENTINE_SPANISH = "argentine_spanish"


class TutorialStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class Customer(BaseModel):
    customer_id: str

    document_number: str
    document_type: str

    first_name: str
    last_name: str

    date_of_birth: date
    gender: Gender

    mobile_phone: str | None = None

    city: str
    state: str
    country: str

    detected_accent: Accent

    segment: str

    registration_date: datetime
    registration_branch_id: int

    customer_status: str

    onboarding_completed: bool = False
    tutorial_version: int = 0
    tutorial_status: TutorialStatus = TutorialStatus.NOT_STARTED
    tutorial_last_completed_step: str | None = None

    last_updated: datetime

    @property
    def is_judge_profile(self) -> bool:
        return self.document_type == "FACTORED_ID"
