from datetime import UTC, datetime

from webapp.backend.models.customer import Customer, TutorialStatus
from webapp.backend.repositories.interfaces import CustomerRepository
from webapp.backend.schemas.onboarding import TutorialProgressRequest, TutorialStateResponse

TUTORIAL_VERSION = 1
TUTORIAL_STEP_IDS = (
    "welcome",
    "menu",
    "cards-link",
    "cards",
    "transactions-link",
    "transactions",
    "report-transaction",
    "izzy",
    "complaints",
    "profile",
    "replay",
)


class InvalidTutorialStepError(ValueError):
    pass


class OnboardingService:
    def __init__(self, customers: CustomerRepository) -> None:
        self.customers = customers

    def state(self, customer: Customer) -> TutorialStateResponse:
        if customer.tutorial_version != TUTORIAL_VERSION:
            return TutorialStateResponse(
                version=TUTORIAL_VERSION,
                status=TutorialStatus.NOT_STARTED,
                last_completed_step=None,
                should_offer=True,
            )

        return TutorialStateResponse(
            version=TUTORIAL_VERSION,
            status=customer.tutorial_status,
            last_completed_step=customer.tutorial_last_completed_step,
            should_offer=customer.tutorial_status is TutorialStatus.NOT_STARTED,
        )

    def update(
        self,
        customer: Customer,
        request: TutorialProgressRequest,
    ) -> TutorialStateResponse:
        step = request.last_completed_step
        if step is not None and step not in TUTORIAL_STEP_IDS:
            raise InvalidTutorialStepError("Unknown tutorial step.")

        completed = request.status in {
            TutorialStatus.COMPLETED,
            TutorialStatus.SKIPPED,
        }
        updated = customer.model_copy(
            update={
                "onboarding_completed": customer.onboarding_completed or completed,
                "tutorial_version": TUTORIAL_VERSION,
                "tutorial_status": request.status,
                "tutorial_last_completed_step": step,
                "last_updated": datetime.now(UTC),
            }
        )
        self.customers.update(updated)
        return self.state(updated)
