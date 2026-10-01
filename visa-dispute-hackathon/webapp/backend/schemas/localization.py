from pydantic import BaseModel


class LocaleContextResponse(BaseModel):
    locale: str
    language: str
    country_code: str | None
    source: str
