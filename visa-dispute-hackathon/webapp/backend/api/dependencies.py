from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status

from webapp.backend.models.customer import Customer
from webapp.backend.models.session import CustomerSession
from webapp.backend.repositories.mock import (
    customer_repository,
    session_repository,
)
from webapp.backend.services.auth import (
    AuthenticationService,
)

SESSION_COOKIE_NAME = "factored_session"


authentication_service = AuthenticationService(
    customer_repository,
    session_repository,
)


@dataclass(frozen=True)
class AuthenticatedContext:
    customer: Customer
    session: CustomerSession


def require_authenticated_context(
    factored_session: Annotated[str | None, Cookie()] = None,
) -> AuthenticatedContext:
    if not factored_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    authenticated = authentication_service.authenticate_with_session(factored_session)
    if authenticated is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid.",
        )

    customer, session = authenticated
    return AuthenticatedContext(customer=customer, session=session)


def require_customer(
    context: Annotated[AuthenticatedContext, Depends(require_authenticated_context)],
) -> Customer:
    return context.customer
