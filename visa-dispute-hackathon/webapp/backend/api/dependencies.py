from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status

from webapp.backend.models.customer import Customer
from webapp.backend.models.session import CustomerSession
from webapp.backend.repositories.interfaces import Repositories
from webapp.backend.services.auth import (
    AuthenticationService,
)

SESSION_COOKIE_NAME = "factored_session"


def get_repositories(request: Request) -> Repositories:
    """Repositories opened by the application lifespan (see `main.py`)."""

    repositories = getattr(request.app.state, "repositories", None)
    if repositories is None:
        raise RuntimeError("The database repositories were not opened at application startup.")
    return repositories


RepositoriesDependency = Annotated[Repositories, Depends(get_repositories)]


def get_authentication_service(repositories: RepositoriesDependency) -> AuthenticationService:
    return AuthenticationService(repositories.customers, repositories.sessions)


AuthenticationServiceDependency = Annotated[
    AuthenticationService, Depends(get_authentication_service)
]


@dataclass(frozen=True)
class AuthenticatedContext:
    customer: Customer
    session: CustomerSession


def require_authenticated_context(
    authentication_service: AuthenticationServiceDependency,
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
