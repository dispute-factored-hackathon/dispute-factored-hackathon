from pydantic import BaseModel


class OnboardingStateResponse(BaseModel):
    onboarding_completed: bool


class CompleteOnboardingResponse(BaseModel):
    onboarding_completed: bool
