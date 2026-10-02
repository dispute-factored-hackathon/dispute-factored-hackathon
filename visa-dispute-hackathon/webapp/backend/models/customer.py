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


class InterfaceLocale(StrEnum):
    ENGLISH = "en-US"
    PORTUGUESE = "pt-BR"
    SPANISH = "es-419"
    MEXICAN_SPANISH = "es-MX"
    COLOMBIAN_SPANISH = "es-CO"
    ARGENTINE_SPANISH = "es-AR"


LOCALE_BY_ACCENT = {
    Accent.PORTUGUESE: InterfaceLocale.PORTUGUESE,
    Accent.MEXICAN_SPANISH: InterfaceLocale.MEXICAN_SPANISH,
    Accent.COLOMBIAN_SPANISH: InterfaceLocale.COLOMBIAN_SPANISH,
    Accent.ARGENTINE_SPANISH: InterfaceLocale.ARGENTINE_SPANISH,
    Accent.ENGLISH: InterfaceLocale.ENGLISH,
}


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

    preferred_locale: InterfaceLocale | None = None

    onboarding_completed: bool = False
    tutorial_version: int = 0
    tutorial_status: TutorialStatus = TutorialStatus.NOT_STARTED
    tutorial_last_completed_step: str | None = None

    last_updated: datetime

    @property
    def is_judge_profile(self) -> bool:
        return self.document_type == "FACTORED_ID"

    @property
    def interface_locale(self) -> InterfaceLocale:
        return self.preferred_locale or LOCALE_BY_ACCENT[self.detected_accent]
