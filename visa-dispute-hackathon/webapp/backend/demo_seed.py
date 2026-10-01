from datetime import UTC, date, datetime

from webapp.backend.models.customer import Accent, Customer, Gender
from webapp.backend.repositories.interfaces import CustomerRepository

DEMO_CUSTOMERS = (
    {
        "customer_id": "DEMO-BR-ANA-1001",
        "document_number": "410001",
        "first_name": "Ana Júlia",
        "last_name": "Santos",
        "country": "Brazil",
        "city": "São Paulo",
        "state": "SP",
        "accent": Accent.PORTUGUESE,
        "phone": "+5511900001001",
    },
    {
        "customer_id": "DEMO-BR-ANA-1002",
        "document_number": "410002",
        "first_name": "Ana Júlia",
        "last_name": "Santos",
        "country": "Brazil",
        "city": "Recife",
        "state": "PE",
        "accent": Accent.PORTUGUESE,
        "phone": "+5581900001002",
    },
    {
        "customer_id": "DEMO-CO-JOSE-2001",
        "document_number": "420001",
        "first_name": "José María",
        "last_name": "Pérez López",
        "country": "Colombia",
        "city": "Bogotá",
        "state": "Bogotá D.C.",
        "accent": Accent.COLOMBIAN_SPANISH,
        "phone": "+573009000001",
    },
    {
        "customer_id": "DEMO-MX-XIMENA-3001",
        "document_number": "430001",
        "first_name": "Ximena",
        "last_name": "Hernández Ruiz",
        "country": "Mexico",
        "city": "Ciudad de México",
        "state": "CDMX",
        "accent": Accent.MEXICAN_SPANISH,
        "phone": "+525590000001",
    },
    {
        "customer_id": "DEMO-US-JORDAN-4001",
        "document_number": "440001",
        "first_name": "Jordan",
        "last_name": "Taylor",
        "country": "United States",
        "city": "Austin",
        "state": "TX",
        "accent": Accent.ENGLISH,
        "phone": "+15129000001",
    },
)


def seed_demo_customers(customers: CustomerRepository) -> None:
    now = datetime.now(UTC)
    for data in DEMO_CUSTOMERS:
        if customers.get_by_id(data["customer_id"]):
            continue
        customers.create(
            Customer(
                customer_id=data["customer_id"],
                document_number=data["document_number"],
                document_type="DEMO_ID",
                first_name=data["first_name"],
                last_name=data["last_name"],
                date_of_birth=date(1990, 1, 1),
                gender=Gender.PREFER_NOT_TO_SAY,
                mobile_phone=data["phone"],
                city=data["city"],
                state=data["state"],
                country=data["country"],
                detected_accent=data["accent"],
                segment="Hackathon demo",
                registration_date=now,
                registration_branch_id=1,
                customer_status="Active",
                onboarding_completed=True,
                last_updated=now,
            )
        )
