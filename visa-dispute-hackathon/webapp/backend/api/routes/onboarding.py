from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from webapp.backend.api.dependencies import (
    AuthenticatedContext,
    require_authenticated_context,
)
from webapp.backend.models.customer import TutorialStatus
from webapp.backend.models.session import AuthenticationMethod
from webapp.backend.repositories.mock import (
    customer_repository,
)
from webapp.backend.schemas.onboarding import TutorialProgressRequest, TutorialStateResponse
from webapp.backend.services.onboarding import InvalidTutorialStepError, OnboardingService

router = APIRouter(
    prefix="/api/onboarding",
    tags=["onboarding"],
)

onboarding_service = OnboardingService(customer_repository)


@router.get(
    "/tour",
    response_model=TutorialStateResponse,
)
def get_tutorial_state(
    context: Annotated[AuthenticatedContext, Depends(require_authenticated_context)],
) -> TutorialStateResponse:
    if context.session.authentication_method is not AuthenticationMethod.FACTORED_ID:
        return TutorialStateResponse(
            version=onboarding_service.version,
            status=TutorialStatus.NOT_STARTED,
            last_completed_step=None,
            should_offer=False,
            eligible=False,
        )
    return onboarding_service.state(context.customer)


@router.patch(
    "/tour",
    response_model=TutorialStateResponse,
)
def update_tutorial_progress(
    request: TutorialProgressRequest,
    context: Annotated[AuthenticatedContext, Depends(require_authenticated_context)],
) -> TutorialStateResponse:
    if context.session.authentication_method is not AuthenticationMethod.FACTORED_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The guided tour is available after signing in with a Factored ID.",
        )
    try:
        return onboarding_service.update(context.customer, request)
    except InvalidTutorialStepError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
