from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from webapp.backend.api.dependencies import (
    require_customer,
)
from webapp.backend.models.customer import Customer, TutorialStatus
from webapp.backend.repositories.mock import (
    customer_repository,
)
from webapp.backend.schemas.onboarding import (
    CompleteOnboardingResponse,
    OnboardingStateResponse,
    TutorialProgressRequest,
    TutorialStateResponse,
)
from webapp.backend.services.onboarding import InvalidTutorialStepError, OnboardingService

router = APIRouter(
    prefix="/api/onboarding",
    tags=["onboarding"],
)

onboarding_service = OnboardingService(customer_repository)


@router.get(
    "",
    response_model=OnboardingStateResponse,
)
def get_onboarding_state(
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
) -> OnboardingStateResponse:
    return OnboardingStateResponse(
        onboarding_completed=(customer.onboarding_completed),
    )


@router.post(
    "/complete",
    response_model=CompleteOnboardingResponse,
)
def complete_onboarding(
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
) -> CompleteOnboardingResponse:
    onboarding_service.update(
        customer,
        TutorialProgressRequest(
            status=TutorialStatus.COMPLETED,
            last_completed_step="replay",
        ),
    )

    return CompleteOnboardingResponse(
        onboarding_completed=True,
    )


@router.get(
    "/tour",
    response_model=TutorialStateResponse,
)
def get_tutorial_state(
    customer: Annotated[Customer, Depends(require_customer)],
) -> TutorialStateResponse:
    return onboarding_service.state(customer)


@router.patch(
    "/tour",
    response_model=TutorialStateResponse,
)
def update_tutorial_progress(
    request: TutorialProgressRequest,
    customer: Annotated[Customer, Depends(require_customer)],
) -> TutorialStateResponse:
    try:
        return onboarding_service.update(customer, request)
    except InvalidTutorialStepError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
