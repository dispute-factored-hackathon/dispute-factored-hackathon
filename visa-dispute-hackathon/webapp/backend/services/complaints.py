from webapp.backend.models.complaint import Complaint
from webapp.backend.repositories.interfaces import (
    ComplaintRepository,
)


class ComplaintNotFoundError(Exception):
    pass


class ComplaintAccessDeniedError(Exception):
    pass


class ComplaintService:
    def __init__(
        self,
        complaints: ComplaintRepository,
    ) -> None:
        self.complaints = complaints

    def list_customer_complaints(
        self,
        customer_id: str,
    ) -> list[Complaint]:
        return self.complaints.list_by_customer(customer_id)

    def get_customer_complaint(
        self,
        complaint_id: str,
        customer_id: str,
    ) -> Complaint:
        complaint = self.complaints.get_by_id(complaint_id)

        if complaint is None:
            raise ComplaintNotFoundError

        if complaint.customer_id != customer_id:
            raise ComplaintAccessDeniedError

        return complaint
