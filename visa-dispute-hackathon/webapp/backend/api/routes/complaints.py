from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from webapp.backend.api.dependencies import (
    RepositoriesDependency,
    require_customer,
)
from webapp.backend.models.complaint import Complaint
from webapp.backend.models.customer import Customer
from webapp.backend.schemas.complaint import (
    ComplaintDetailResponse,
    ComplaintListItemResponse,
)
from webapp.backend.services.complaints import (
    ComplaintAccessDeniedError,
    ComplaintNotFoundError,
    ComplaintService,
)

router = APIRouter(
    prefix="/api/complaints",
    tags=["complaints"],
)


def get_complaint_service(repositories: RepositoriesDependency) -> ComplaintService:
    return ComplaintService(repositories.complaints)


ComplaintServiceDependency = Annotated[ComplaintService, Depends(get_complaint_service)]


def list_response(
    complaint: Complaint,
) -> ComplaintListItemResponse:
    return ComplaintListItemResponse(
        complaint_id=complaint.complaint_id,
        creation_date=complaint.creation_date,
        case_type=complaint.case_type,
        category=complaint.category,
        subcategory=complaint.subcategory,
        claimed_amount=complaint.claimed_amount,
        currency=complaint.currency,
        status=complaint.status,
        priority=complaint.priority,
    )


def detail_response(
    complaint: Complaint,
) -> ComplaintDetailResponse:
    return ComplaintDetailResponse(
        complaint_id=complaint.complaint_id,
        creation_date=complaint.creation_date,
        case_type=complaint.case_type,
        category=complaint.category,
        subcategory=complaint.subcategory,
        reception_channel=(complaint.reception_channel),
        affected_product_id=(complaint.affected_product_id),
        description=complaint.description,
        claimed_amount=(complaint.claimed_amount),
        currency=complaint.currency,
        priority=complaint.priority,
        status=complaint.status,
        assignment_date=(complaint.assignment_date),
        first_response_date=(complaint.first_response_date),
        resolution_date=(complaint.resolution_date),
        closing_date=(complaint.closing_date),
        sla_breached=complaint.sla_breached,
        resolution_days=(complaint.resolution_days),
        resolution=complaint.resolution,
        compensation_granted=(complaint.compensation_granted),
        resolution_satisfaction=(complaint.resolution_satisfaction),
    )


@router.get(
    "",
    response_model=list[ComplaintListItemResponse],
)
def list_complaints(
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
    complaint_service: ComplaintServiceDependency,
) -> list[ComplaintListItemResponse]:
    complaints = complaint_service.list_customer_complaints(customer.customer_id)

    return [list_response(complaint) for complaint in complaints]


@router.get(
    "/{complaint_id}",
    response_model=ComplaintDetailResponse,
)
def get_complaint(
    complaint_id: str,
    customer: Annotated[
        Customer,
        Depends(require_customer),
    ],
    complaint_service: ComplaintServiceDependency,
) -> ComplaintDetailResponse:
    try:
        complaint = complaint_service.get_customer_complaint(
            complaint_id,
            customer.customer_id,
        )

    except (
        ComplaintNotFoundError,
        ComplaintAccessDeniedError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found.",
        ) from error

    return detail_response(complaint)
