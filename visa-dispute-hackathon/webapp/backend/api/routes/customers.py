from fastapi import (
    APIRouter,
    HTTPException,
    status,
)

from webapp.backend.repositories.mock import (
    complaint_repository,
    customer_repository,
    product_repository,
    transaction_repository,
)
from webapp.backend.schemas.customer import (
    CustomerSignupRequest,
    CustomerSignupResponse,
)
from webapp.backend.services.signup import (
    SignupService,
)

router = APIRouter(
    prefix="/api/customers",
    tags=["customers"],
)


signup_service = SignupService(
    customer_repository,
    product_repository,
    transaction_repository,
    complaint_repository,
)


@router.post(
    "",
    response_model=CustomerSignupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    request: CustomerSignupRequest,
) -> CustomerSignupResponse:
    try:
        return signup_service.signup(request)

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
