from fastapi import APIRouter, Request

from webapp.backend.schemas.localization import LocaleContextResponse
from webapp.backend.services.localization import (
    country_for_request,
    language_for_locale,
    locale_for_country,
)

router = APIRouter(prefix="/api/localization", tags=["localization"])


@router.get("/context", response_model=LocaleContextResponse)
def locale_context(request: Request) -> LocaleContextResponse:
    client_ip = request.client.host if request.client is not None else None
    country_code, source = country_for_request(request.headers, client_ip)
    locale = locale_for_country(country_code)
    return LocaleContextResponse(
        locale=locale.value,
        language=language_for_locale(locale),
        country_code=country_code,
        source=source,
    )
