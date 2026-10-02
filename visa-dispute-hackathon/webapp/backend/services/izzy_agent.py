"""Canonical synthetic service-agent record for the Izzy demo assistant."""

from datetime import date

from webapp.backend.models.service_agent import ServiceAgent
from webapp.backend.repositories.interfaces import ServiceAgentRepository

IZZY_AGENT_ID = "AGENT-IZZY"
IZZY_EMPLOYEE_CODE = "IZZY-AI-001"


def izzy_record() -> ServiceAgent:
    return ServiceAgent(
        agent_id=IZZY_AGENT_ID,
        employee_code=IZZY_EMPLOYEE_CODE,
        first_name="Izzy",
        last_name="Factored",
        email="izzy@factored.demo",
        native_accent="Multilingual",
        country_of_origin="Synthetic",
        agent_type="Hybrid",
        experience_level="Specialist",
        languages="English, Portuguese, Spanish",
        specialty="Card Disputes",
        hire_date=date(2026, 1, 1),
        avg_csat=None,
        total_monthly_interactions=0,
        agent_status="Active",
        work_shift="Always-on",
    )


def seed_izzy_agent(repository: ServiceAgentRepository) -> ServiceAgent:
    """Create Izzy once while preserving accumulated operational metrics."""

    existing = repository.get_by_id(IZZY_AGENT_ID)
    if existing is not None:
        return existing
    return repository.create(izzy_record())
