import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from webapp.backend.models.customer import Accent, Gender

PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class CustomerProfileUpdateRequest(BaseModel):
    """Editable profile fields. Identifiers are intentionally not accepted."""

    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    gender: Gender
    mobile_phone: str | None = None
    preferred_accent: Accent

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Name cannot be empty.")
        return normalized.title()

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError("Birth date must be in the past.")
        return value

    @field_validator("mobile_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("Phone must use international format, for example +5511999999999.")
        return normalized


class CustomerProfileResponse(BaseModel):
    customer_id: str
    factored_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender
    mobile_phone: str | None
    preferred_accent: Accent
    customer_status: str


class CustomerSignupRequest(BaseModel):
    first_name: str = Field(
        min_length=1,
        max_length=100,
    )
    last_name: str = Field(
        min_length=1,
        max_length=100,
    )

    date_of_birth: date
    gender: Gender

    mobile_phone: str | None = None
    preferred_accent: Accent

    factored_id: str = Field(
        pattern=r"^\d{6}$",
    )

    @field_validator(
        "first_name",
        "last_name",
    )
    @classmethod
    def normalize_name(
        cls,
        value: str,
    ) -> str:
        value = " ".join(value.split())

        if not value:
            raise ValueError("Name cannot be empty.")

        return value.title()

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(
        cls,
        value: date,
    ) -> date:
        if value >= date.today():
            raise ValueError("Birth date must be in the past.")

        return value

    @field_validator("mobile_phone")
    @classmethod
    def validate_phone(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        if not PHONE_PATTERN.fullmatch(value):
            raise ValueError("Phone must use international format, for example +5511999999999.")

        return value


class DemoCardResponse(BaseModel):
    product_id: str
    last_four: str
    product_type: str
    currency: str
    product_status: str


class CustomerSignupResponse(BaseModel):
    customer_id: str

    first_name: str
    last_name: str

    factored_id: str
    mobile_phone: str | None
    preferred_accent: Accent

    customer_status: str

    demo_card: DemoCardResponse
