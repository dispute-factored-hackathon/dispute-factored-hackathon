from datetime import UTC, datetime

from webapp.backend.models.customer import LOCALE_BY_ACCENT, Customer
from webapp.backend.repositories.interfaces import CustomerRepository
from webapp.backend.schemas.customer import CustomerProfileUpdateRequest


class PhoneAlreadyRegisteredError(Exception):
    pass


class CustomerProfileService:
    def __init__(self, customers: CustomerRepository) -> None:
        self.customers = customers

    def update(
        self,
        customer: Customer,
        request: CustomerProfileUpdateRequest,
    ) -> Customer:
        if request.mobile_phone:
            owner = self.customers.get_by_phone(request.mobile_phone)
            if owner is not None and owner.customer_id != customer.customer_id:
                raise PhoneAlreadyRegisteredError

        updated = customer.model_copy(
            update={
                "first_name": request.first_name,
                "last_name": request.last_name,
                "date_of_birth": request.date_of_birth,
                "gender": request.gender,
                "mobile_phone": request.mobile_phone,
                "detected_accent": request.preferred_accent,
                "preferred_locale": request.preferred_locale
                or LOCALE_BY_ACCENT[request.preferred_accent],
                "last_updated": datetime.now(UTC),
            }
        )
        return self.customers.update(updated)
