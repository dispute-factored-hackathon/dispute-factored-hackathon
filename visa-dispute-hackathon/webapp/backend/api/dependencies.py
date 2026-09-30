from typing import Annotated

from fastapi import Cookie, HTTPException, status

from webapp.backend.models.customer import Customer
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


def require_customer(
    factored_session: Annotated[
        str | None,
        Cookie(),
    ] = None,
) -> Customer:
    if not factored_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    customer = authentication_service.authenticate(factored_session)

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid.",
        )

    return customer
