from pydantic import BaseModel, Field


class IzzyContactResponse(BaseModel):
    phone_number: str
    phone_display: str


class IzzySessionRequest(BaseModel):
    # A transaction the customer opened in the web app; ignored unless it is theirs.
    transaction_id: str | None = Field(default=None, min_length=1, max_length=80)
    # The interface locale the customer is reading (en-US, pt-BR, es-CO, ...).
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Za-z0-9]{2,3})?$")


class IzzySessionResponse(BaseModel):
    session_id: str
    message: str
    stage: str
    language: str
    transaction_context: bool
    phone_number: str
    phone_display: str


class IzzyMessageRequest(BaseModel):
    # Hard transport cap; the chat answers longer-than-allowed messages with a friendly prompt.
    message: str = Field(max_length=4_000)
