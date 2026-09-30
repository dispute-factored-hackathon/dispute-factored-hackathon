from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Response,
    status,
)

from webapp.backend.api.dependencies import (
    SESSION_COOKIE_NAME,
    authentication_service,
    require_customer,
)
from webapp.backend.config import get_settings
from webapp.backend.models.customer import Customer
from webapp.backend.schemas.auth import (
    AuthenticatedCustomerResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
)
from webapp.backend.services.auth import (
    AuthenticationError,
)

router = APIRouter(
    prefix="/api/auth",
    tags=["authentication"],
)

settings = get_settings()


def customer_response(
    customer: Customer,
) -> AuthenticatedCustomerResponse:
    return AuthenticatedCustomerResponse(
        customer_id=customer.customer_id,
        factored_id=customer.document_number,
        first_name=customer.first_name,
        last_name=customer.last_name,
        preferred_accent=(customer.detected_accent.value),
        onboarding_completed=(customer.onboarding_completed),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    request: LoginRequest,
    response: Response,
) -> LoginResponse:
    try:
        customer, session = authentication_service.login(request.factored_id)

    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=(settings.session_duration_hours * 60 * 60),
        path="/",
    )

    return LoginResponse(
        authenticated=True,
        customer=customer_response(customer),
    )


@router.get(
    "/me",
    response_model=AuthenticatedCustomerResponse,
)
def me(
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
) -> AuthenticatedCustomerResponse:
    return customer_response(customer)


@router.post(
    "/logout",
    response_model=LogoutResponse,
)
def logout(
    response: Response,
    factored_session: Annotated[
        str | None,
        Cookie(),
    ] = None,
) -> LogoutResponse:
    if factored_session:
        authentication_service.logout(factored_session)

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        samesite="lax",
    )

    return LogoutResponse(
        authenticated=False,
    )
