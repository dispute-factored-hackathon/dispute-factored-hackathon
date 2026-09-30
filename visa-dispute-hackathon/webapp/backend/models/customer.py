from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel


class Gender(StrEnum):
    FEMALE = "female"
    MALE = "male"
    NON_BINARY = "non_binary"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class Accent(StrEnum):
    ENGLISH = "english"
    PORTUGUESE = "portuguese"
    MEXICAN_SPANISH = "mexican_spanish"
    COLOMBIAN_SPANISH = "colombian_spanish"
    ARGENTINE_SPANISH = "argentine_spanish"


class Customer(BaseModel):
    customer_id: str

    document_number: str
    document_type: str

    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender

    mobile_phone: str | None

    city: str
    state: str
    country: str

    detected_accent: Accent

    segment: str
    registration_date: datetime
    registration_branch_id: int
    customer_status: str
    last_updated: datetime
