"""Deterministic synthetic caller identification by phone or document."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class CallerIdentityStatus(StrEnum):
    AUTHENTICATED = "authenticated"
    NEEDS_DOCUMENT = "needs_document"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class CallerIdentity:
    customer_id: str
    full_name: str
    country: str | None
    detected_accent: str | None
    assurance_level: str


@dataclass(frozen=True)
class CallerIdentityResult:
    status: CallerIdentityStatus
    identity: CallerIdentity | None = None
    country_code: str | None = None


@dataclass(frozen=True)
class _CallerRecord:
    customer_id: str
    full_name: str
    mobile_phone: str
    document_number: str
    country: str | None
    detected_accent: str | None


def normalize_phone(value: str) -> str:
    """Normalize a supplied international phone number for exact lookup."""

    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 8 or len(digits) > 15:
        raise ValueError("mobile phone must contain 8 to 15 digits")
    return f"+{digits}"


def calling_code_from_phone(value: str) -> str | None:
    """Return a calling-code hint without claiming verified location."""

    phone = normalize_phone(value)
    for code in ("+351", "+55", "+57", "+52", "+54", "+34", "+1"):
        if phone.startswith(code):
            return code
    match = re.match(r"^\+(\d{1,3})", phone)
    return f"+{match.group(1)}" if match else None


def normalize_document(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


class VoiceCallerIdentityService:
    """Authenticate a synthetic call by caller phone, then document fallback."""

    def __init__(self, customers_csv: str | Path) -> None:
        self.customers_csv = Path(customers_csv)
        self._records = self._load()

    def _load(self) -> tuple[_CallerRecord, ...]:
        with self.customers_csv.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {
                "customer_id",
                "first_name",
                "last_name",
                "mobile_phone",
                "document_number",
            }
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"Customers CSV is missing columns: {sorted(missing)}")
            records = []
            for row in reader:
                if row.get("customer_status", "Active").strip().casefold() != "active":
                    continue
                phone = (row.get("mobile_phone") or "").strip()
                document = normalize_document(row.get("document_number") or "")
                if not document:
                    continue
                records.append(
                    _CallerRecord(
                        customer_id=row["customer_id"].strip(),
                        full_name=" ".join((row["first_name"].strip(), row["last_name"].strip())),
                        mobile_phone=normalize_phone(phone) if phone else "",
                        document_number=document,
                        country=(row.get("country") or "").strip() or None,
                        detected_accent=(row.get("detected_accent") or "").strip() or None,
                    )
                )
        return tuple(records)

    def identify_phone(self, mobile_phone: str) -> CallerIdentityResult:
        normalized = normalize_phone(mobile_phone)
        matches = [record for record in self._records if record.mobile_phone == normalized]
        if len(matches) == 1:
            return CallerIdentityResult(
                CallerIdentityStatus.AUTHENTICATED,
                self._identity(matches[0], "DEMO_ONLY_PHONE_MATCH"),
                calling_code_from_phone(normalized),
            )
        return CallerIdentityResult(
            CallerIdentityStatus.AMBIGUOUS if matches else CallerIdentityStatus.NEEDS_DOCUMENT,
            country_code=calling_code_from_phone(normalized),
        )

    def identify_document(self, document_number: str) -> CallerIdentityResult:
        normalized = normalize_document(document_number)
        if not normalized:
            return CallerIdentityResult(CallerIdentityStatus.NOT_FOUND)
        matches = [record for record in self._records if record.document_number == normalized]
        if len(matches) == 1:
            return CallerIdentityResult(
                CallerIdentityStatus.AUTHENTICATED,
                self._identity(matches[0], "DEMO_ONLY_DOCUMENT_MATCH"),
            )
        return CallerIdentityResult(
            CallerIdentityStatus.AMBIGUOUS if matches else CallerIdentityStatus.NOT_FOUND
        )

    @staticmethod
    def _identity(record: _CallerRecord, assurance: str) -> CallerIdentity:
        return CallerIdentity(
            customer_id=record.customer_id,
            full_name=record.full_name,
            country=record.country,
            detected_accent=record.detected_accent,
            assurance_level=assurance,
        )
