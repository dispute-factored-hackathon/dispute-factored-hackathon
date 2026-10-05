from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from webapp.backend.api.dependencies import (
    AuthenticatedContext,
    RepositoriesDependency,
    require_authenticated_context,
)
from webapp.backend.models.customer import TutorialStatus
from webapp.backend.schemas.onboarding import TutorialProgressRequest, TutorialStateResponse
from webapp.backend.services.onboarding import (
    InvalidTutorialStepError,
    OnboardingService,
    onboarding_eligible,
)

router = APIRouter(
    prefix="/api/onboarding",
    tags=["onboarding"],
)


def get_onboarding_service(repositories: RepositoriesDependency) -> OnboardingService:
    return OnboardingService(repositories.customers)


OnboardingServiceDependency = Annotated[OnboardingService, Depends(get_onboarding_service)]


@router.get(
    "/tour",
    response_model=TutorialStateResponse,
)
def get_tutorial_state(
    context: Annotated[AuthenticatedContext, Depends(require_authenticated_context)],
    onboarding_service: OnboardingServiceDependency,
) -> TutorialStateResponse:
    if not onboarding_eligible(context.customer, context.session.authentication_method):
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
    onboarding_service: OnboardingServiceDependency,
) -> TutorialStateResponse:
    if not onboarding_eligible(context.customer, context.session.authentication_method):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The guided tour is not available for this session.",
        )
    try:
        return onboarding_service.update(context.customer, request)
    except InvalidTutorialStepError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
