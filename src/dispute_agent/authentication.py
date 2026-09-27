"""Mock, name-based customer identification for the hackathon agent."""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class AuthStatus(StrEnum):
    NEEDS_NAME = "needs_name"
    AUTHENTICATED = "authenticated"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    HUMAN_HANDOFF = "human_handoff"


@dataclass(frozen=True)
class CustomerMatch:
    customer_id: str
    full_name: str


@dataclass(frozen=True)
class AuthenticationResult:
    status: AuthStatus
    message: str
    customer: CustomerMatch | None = None
    assurance_level: str | None = None

    @property
    def authenticated(self) -> bool:
        return self.status is AuthStatus.AUTHENTICATED


def normalize_name(value: str) -> str:
    """Normalize spacing, case and diacritics for deterministic name matching."""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.casefold()
    value = re.sub(r"[^\w\s'-]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _looks_like_avoidance(answer: str) -> bool:
    normalized = normalize_name(answer)
    if not normalized:
        return True
    phrases = (
        "i do not want", "i dont want", "rather not", "not telling",
        "why do you need", "why should i", "skip", "prefer not",
        "no quiero", "prefiero no", "por que necesitas",
        "nao quero", "prefiro nao", "por que precisa",
    )
    return any(phrase in normalized for phrase in phrases)


class CustomerDirectory:
    """Read-only name index backed by the synthetic customers CSV."""

    def __init__(self, customers_csv: str | Path):
        self.customers_csv = Path(customers_csv)
        self._customers_by_name = self._load()

    def _load(self) -> dict[str, list[CustomerMatch]]:
        if not self.customers_csv.is_file():
            raise FileNotFoundError(f"Customers CSV not found: {self.customers_csv}")
        index: dict[str, list[CustomerMatch]] = {}
        with self.customers_csv.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"customer_id", "first_name", "last_name"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"Customers CSV is missing columns: {sorted(missing)}")
            for row in reader:
                full_name = " ".join((row["first_name"].strip(), row["last_name"].strip()))
                key = normalize_name(full_name)
                if key:
                    index.setdefault(key, []).append(
                        CustomerMatch(customer_id=row["customer_id"], full_name=full_name)
                    )
        return index

    def find_by_full_name(self, full_name: str) -> list[CustomerMatch]:
        return list(self._customers_by_name.get(normalize_name(full_name), []))


class AuthenticationAgent:
    """Stateful demo-only name-identification conversation for one caller."""

    QUESTION = "What is your full name?"

    def __init__(self, customers_csv: str | Path, *, max_failed_attempts: int = 2, max_avoidance_attempts: int = 2):
        self.directory = CustomerDirectory(customers_csv)
        self.max_failed_attempts = max_failed_attempts
        self.max_avoidance_attempts = max_avoidance_attempts
        self.failed_attempts = 0
        self.avoidance_attempts = 0
        self.current_customer: CustomerMatch | None = None

    def start(self) -> AuthenticationResult:
        return AuthenticationResult(AuthStatus.NEEDS_NAME, self.QUESTION)

    def handle_answer(self, answer: str | None) -> AuthenticationResult:
        if self.current_customer is not None:
            return AuthenticationResult(
                AuthStatus.AUTHENTICATED,
                f"Demo customer already identified as {self.current_customer.full_name}.",
                self.current_customer,
                "DEMO_ONLY_NAME_MATCH",
            )

        answer = answer or ""
        if _looks_like_avoidance(answer):
            self.avoidance_attempts += 1
            if self.avoidance_attempts >= self.max_avoidance_attempts:
                return AuthenticationResult(
                    AuthStatus.HUMAN_HANDOFF,
                    "I cannot access transactions without a full name. I will transfer you to a human for mock assistance.",
                )
            return AuthenticationResult(
                AuthStatus.NEEDS_NAME,
                "I need your full name to find your synthetic customer record. You may also ask for a human. What is your full name?",
            )

        matches = self.directory.find_by_full_name(answer)
        if len(matches) == 1:
            self.current_customer = matches[0]
            return AuthenticationResult(
                AuthStatus.AUTHENTICATED,
                f"Thank you. I found the synthetic customer record for {matches[0].full_name}.",
                matches[0],
                "DEMO_ONLY_NAME_MATCH",
            )
        if len(matches) > 1:
            return AuthenticationResult(
                AuthStatus.AMBIGUOUS,
                "I found more than one synthetic customer with that name. A human must resolve the ambiguity before transactions are shown.",
            )

        self.failed_attempts += 1
        if self.failed_attempts >= self.max_failed_attempts:
            return AuthenticationResult(
                AuthStatus.HUMAN_HANDOFF,
                "I could not find a unique synthetic customer after multiple attempts. I will transfer you to a human for mock assistance.",
            )
        return AuthenticationResult(
            AuthStatus.NOT_FOUND,
            "I could not find that full name in the synthetic customer database. Please check the name and try once more.",
        )
