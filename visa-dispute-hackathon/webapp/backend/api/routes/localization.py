from fastapi import APIRouter, Request

from webapp.backend.schemas.localization import LocaleContextResponse
from webapp.backend.services.localization import (
    country_from_headers,
    language_for_locale,
    locale_for_country,
)

router = APIRouter(prefix="/api/localization", tags=["localization"])


@router.get("/context", response_model=LocaleContextResponse)
def locale_context(request: Request) -> LocaleContextResponse:
    country_code, source = country_from_headers(request.headers)
    locale = locale_for_country(country_code)
    return LocaleContextResponse(
        locale=locale.value,
        language=language_for_locale(locale),
        country_code=country_code,
        source=source,
    )
