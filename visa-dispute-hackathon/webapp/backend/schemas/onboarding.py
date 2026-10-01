from pydantic import BaseModel, ConfigDict

from webapp.backend.models.customer import TutorialStatus


class TutorialProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TutorialStatus
    last_completed_step: str | None = None


class TutorialStateResponse(BaseModel):
    version: int
    status: TutorialStatus
    last_completed_step: str | None
    should_offer: bool
    eligible: bool
