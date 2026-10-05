from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from webapp.backend.api.dependencies import RepositoriesDependency, require_customer
from webapp.backend.models.customer import Customer
from webapp.backend.schemas.customer import (
    CustomerProfileResponse,
    CustomerProfileUpdateRequest,
    CustomerSignupRequest,
    CustomerSignupResponse,
)
from webapp.backend.services.profile import CustomerProfileService, PhoneAlreadyRegisteredError
from webapp.backend.services.signup import (
    SignupService,
)

router = APIRouter(
    prefix="/api/customers",
    tags=["customers"],
)


def get_signup_service(repositories: RepositoriesDependency) -> SignupService:
    return SignupService(repositories.account_registration)


def get_profile_service(repositories: RepositoriesDependency) -> CustomerProfileService:
    return CustomerProfileService(repositories.customers)


def profile_response(customer: Customer) -> CustomerProfileResponse:
    return CustomerProfileResponse(
        customer_id=customer.customer_id,
        factored_id=customer.document_number,
        first_name=customer.first_name,
        last_name=customer.last_name,
        date_of_birth=customer.date_of_birth,
        gender=customer.gender,
        mobile_phone=customer.mobile_phone,
        preferred_accent=customer.detected_accent,
        preferred_locale=customer.interface_locale,
        customer_status=customer.customer_status,
    )


@router.post(
    "",
    response_model=CustomerSignupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    request: CustomerSignupRequest,
    signup_service: Annotated[SignupService, Depends(get_signup_service)],
) -> CustomerSignupResponse:
    try:
        return signup_service.signup(request)

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.get(
    "/profile",
    response_model=CustomerProfileResponse,
)
def get_profile(
    customer: Annotated[Customer, Depends(require_customer)],
) -> CustomerProfileResponse:
    return profile_response(customer)


@router.patch(
    "/profile",
    response_model=CustomerProfileResponse,
)
def update_profile(
    request: CustomerProfileUpdateRequest,
    customer: Annotated[Customer, Depends(require_customer)],
    profile_service: Annotated[CustomerProfileService, Depends(get_profile_service)],
) -> CustomerProfileResponse:
    try:
        updated = profile_service.update(customer, request)
    except PhoneAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already exists.",
        ) from error
    return profile_response(updated)
