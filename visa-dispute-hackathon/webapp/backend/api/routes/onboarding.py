from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)

from webapp.backend.api.dependencies import (
    require_customer,
)
from webapp.backend.models.customer import Customer
from webapp.backend.repositories.mock import (
    customer_repository,
)
from webapp.backend.schemas.onboarding import (
    CompleteOnboardingResponse,
    OnboardingStateResponse,
)

router = APIRouter(
    prefix="/api/onboarding",
    tags=["onboarding"],
)


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
    if not customer.onboarding_completed:
        updated = customer.model_copy(
            update={
                "onboarding_completed": True,
                "last_updated": datetime.now(UTC),
            }
        )

        customer_repository.update(updated)

    return CompleteOnboardingResponse(
        onboarding_completed=True,
    )
