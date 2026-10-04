from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class IzzyContactResponse(BaseModel):
    phone_number: str
    phone_display: str


class IzzySessionRequest(BaseModel):
    # A transaction the customer opened in the web app; ignored unless it is theirs.
    transaction_id: str | None = Field(default=None, min_length=1, max_length=80)
    # The interface locale the customer is reading (en-US, pt-BR, es-CO, ...).
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Za-z0-9]{2,3})?$")


class IzzyPurchaseOption(BaseModel):
    """One card purchase Izzy offers for selection (only the card's last four digits)."""

    transaction_id: str
    merchant: str | None
    date: datetime
    amount: float
    currency: str
    city: str | None
    country: str | None
    category: str | None
    channel: str
    card_type: str
    card_last_four: str


class IzzySessionResponse(BaseModel):
    session_id: str
    message: str
    stage: str
    language: str
    transaction_context: bool
    options: list[IzzyPurchaseOption]
    # Set when the chat was opened from a purchase: it is already selected.
    selected_transaction_id: str | None
    phone_number: str
    phone_display: str


class IzzyMessageRequest(BaseModel):
    # Hard transport cap; the chat answers longer-than-allowed messages with a friendly prompt.
    message: str = Field(default="", max_length=4_000)
    # Tapping an offered purchase, or "None of these"; the server accepts only offered options.
    selected_transaction_id: str | None = Field(default=None, min_length=1, max_length=80)
    reject_options: bool = False

    @model_validator(mode="after")
    def _one_action(self) -> "IzzyMessageRequest":
        if self.selected_transaction_id and self.reject_options:
            raise ValueError("choose an option or reject the options, not both")
        return self
