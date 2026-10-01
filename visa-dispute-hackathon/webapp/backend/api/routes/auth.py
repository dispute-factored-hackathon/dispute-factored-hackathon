from typing import Annotated

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)

from webapp.backend.api.dependencies import (
    SESSION_COOKIE_NAME,
    AuthenticatedContext,
    authentication_service,
    require_authenticated_context,
)
from webapp.backend.config import get_settings
from webapp.backend.models.customer import Customer
from webapp.backend.models.session import AuthenticationMethod, CustomerSession
from webapp.backend.schemas.auth import (
    AuthenticatedCustomerResponse,
    DemoLoginOption,
    DemoLoginOptionsResponse,
    DemoLoginRequest,
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


LOCALE_BY_ACCENT = {
    "portuguese": "pt-BR",
    "mexican_spanish": "es-MX",
    "colombian_spanish": "es-CO",
    "argentine_spanish": "es-AR",
    "english": "en-US",
}


def customer_response(
    customer: Customer,
    session: CustomerSession,
) -> AuthenticatedCustomerResponse:
    return AuthenticatedCustomerResponse(
        customer_id=customer.customer_id,
        factored_id=customer.document_number,
        first_name=customer.first_name,
        last_name=customer.last_name,
        preferred_accent=(customer.detected_accent.value),
        locale=LOCALE_BY_ACCENT[customer.detected_accent.value],
        onboarding_completed=(customer.onboarding_completed),
        onboarding_eligible=(session.authentication_method is AuthenticationMethod.FACTORED_ID),
    )


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=(settings.session_duration_hours * 60 * 60),
        path="/",
    )


def login_response(customer: Customer, session: CustomerSession) -> LoginResponse:
    return LoginResponse(
        authenticated=True,
        customer=customer_response(customer, session),
    )


@router.get(
    "/demo-customers",
    response_model=DemoLoginOptionsResponse,
)
def demo_customers(
    q: str = Query(default="", max_length=100),
) -> DemoLoginOptionsResponse:
    options = authentication_service.list_demo_options(q, limit=10)
    return DemoLoginOptionsResponse(
        options=[
            DemoLoginOption(
                selection=selection,
                full_name=f"{customer.first_name} {customer.last_name}",
                disambiguator=(f"{customer.country} · profile {customer.customer_id[-4:]}"),
            )
            for customer, selection in options
        ]
    )


@router.post(
    "/demo-login",
    response_model=LoginResponse,
)
def demo_login(
    request: DemoLoginRequest,
    response: Response,
) -> LoginResponse:
    try:
        customer, session = authentication_service.login_demo_selection(request.selection)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error

    set_session_cookie(response, session.session_id)
    return login_response(customer, session)


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

    set_session_cookie(response, session.session_id)
    return login_response(customer, session)


@router.get(
    "/me",
    response_model=AuthenticatedCustomerResponse,
)
def me(
    context: Annotated[
        AuthenticatedContext,
        Depends(require_authenticated_context),
    ],
) -> AuthenticatedCustomerResponse:
    return customer_response(context.customer, context.session)


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
