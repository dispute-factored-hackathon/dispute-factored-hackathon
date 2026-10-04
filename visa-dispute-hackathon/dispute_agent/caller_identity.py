"""Deterministic synthetic caller identification by phone or document."""

from __future__ import annotations

import csv
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from webapp.backend.models.customer import Customer
from webapp.backend.repositories.interfaces import CustomerRepository

LOGGER = logging.getLogger(__name__)


def _telemetry(event: str, **fields: Any) -> None:
    """Emit identity timing telemetry without phone/document/customer values."""
    payload: dict[str, Any] = {"event": event, **fields}
    LOGGER.info(json.dumps(payload, ensure_ascii=False, default=str))


class CallerIdentityStatus(StrEnum):
    AUTHENTICATED = "authenticated"
    NEEDS_DOCUMENT = "needs_document"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class CallerIdentity:
    customer_id: str
    first_name: str
    last_name: str
    full_name: str
    gender: str | None
    age: int | None
    country: str | None
    detected_accent: str | None
    preferred_locale: str | None
    assurance_level: str


@dataclass(frozen=True)
class CallerIdentityResult:
    status: CallerIdentityStatus
    identity: CallerIdentity | None = None
    country_code: str | None = None


@dataclass(frozen=True)
class _CallerRecord:
    customer_id: str
    first_name: str
    last_name: str
    full_name: str
    mobile_phone: str
    document_number: str
    country: str | None
    detected_accent: str | None
    preferred_locale: str | None


def normalize_phone(value: str) -> str:
    """Normalize a supplied international phone number for exact lookup."""
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 8 or len(digits) > 15:
        raise ValueError("mobile phone must contain 8 to 15 digits")
    return f"+{digits}"


def calling_code_from_phone(value: str) -> str | None:
    """Return a calling-code hint without claiming verified location."""
    phone = normalize_phone(value)

    for code in (
        "+351",
        "+55",
        "+57",
        "+52",
        "+54",
        "+34",
        "+1",
    ):
        if phone.startswith(code):
            return code

    match = re.match(r"^\+(\d{1,3})", phone)
    return f"+{match.group(1)}" if match else None


def normalize_document(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


class VoiceCallerIdentityService:
    """Authenticate a synthetic call by phone or document lookup."""

    def __init__(
        self,
        customer_source: str | Path | CustomerRepository,
    ) -> None:
        started = time.perf_counter()
        self.customers_csv: Path | None = None
        self.customer_repository: CustomerRepository | None = None

        if isinstance(customer_source, (str, Path)):
            self.customers_csv = Path(customer_source)
        else:
            self.customer_repository = customer_source

        load_started = time.perf_counter()
        self._records = self._load() if self.customers_csv else ()
        load_ms = (time.perf_counter() - load_started) * 1000

        index_started = time.perf_counter()
        self._phone_index = self._build_index(
            self._records,
            key=lambda record: record.mobile_phone,
        )
        self._document_index = self._build_index(
            self._records,
            key=lambda record: record.document_number,
        )
        index_ms = (time.perf_counter() - index_started) * 1000

        _telemetry(
            "caller_identity.initialized",
            records=len(self._records) if self.customers_csv else "repository",
            load_ms=round(load_ms, 2),
            index_ms=round(index_ms, 2),
            total_ms=round(
                (time.perf_counter() - started) * 1000,
                2,
            ),
        )

    def _load(self) -> tuple[_CallerRecord, ...]:
        assert self.customers_csv is not None
        with self.customers_csv.open(
            encoding="utf-8-sig",
            newline="",
        ) as stream:
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

            records: list[_CallerRecord] = []

            for row in reader:
                if (
                    row.get(
                        "customer_status",
                        "Active",
                    )
                    .strip()
                    .casefold()
                    != "active"
                ):
                    continue

                phone = (row.get("mobile_phone") or "").strip()

                document = normalize_document(row.get("document_number") or "")

                if not document:
                    continue

                records.append(
                    _CallerRecord(
                        customer_id=row["customer_id"].strip(),
                        first_name=row["first_name"].strip(),
                        last_name=row["last_name"].strip(),
                        full_name=" ".join(
                            (
                                row["first_name"].strip(),
                                row["last_name"].strip(),
                            )
                        ),
                        mobile_phone=(normalize_phone(phone) if phone else ""),
                        document_number=document,
                        country=(row.get("country") or "").strip() or None,
                        detected_accent=(row.get("detected_accent") or "").strip() or None,
                        preferred_locale=(
                            row.get("preferred_locale") or row.get("locale") or ""
                        ).strip()
                        or None,
                    )
                )

        return tuple(records)

    @staticmethod
    def _build_index(
        records: tuple[_CallerRecord, ...],
        *,
        key,
    ) -> dict[str, tuple[_CallerRecord, ...]]:
        mutable: dict[str, list[_CallerRecord]] = {}

        for record in records:
            value = key(record)

            if not value:
                continue

            mutable.setdefault(
                value,
                [],
            ).append(record)

        return {value: tuple(matches) for value, matches in mutable.items()}

    def identify_phone(
        self,
        mobile_phone: str,
    ) -> CallerIdentityResult:
        started = time.perf_counter()
        normalized = normalize_phone(mobile_phone)

        if self.customer_repository is not None:
            customer = self.customer_repository.get_by_phone(normalized)
            matches = (
                (customer,)
                if customer is not None and customer.customer_status.casefold() == "active"
                else ()
            )
            identity = (
                self._identity_from_customer(customer, "DEMO_ONLY_PHONE_MATCH") if matches else None
            )
            result = CallerIdentityResult(
                CallerIdentityStatus.AUTHENTICATED
                if matches
                else CallerIdentityStatus.NEEDS_DOCUMENT,
                identity,
                calling_code_from_phone(normalized),
            )
            _telemetry(
                "caller_identity.phone_lookup",
                status=result.status.value,
                match_count=len(matches),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return result

        matches = self._phone_index.get(
            normalized,
            (),
        )

        if len(matches) == 1:
            result = CallerIdentityResult(
                CallerIdentityStatus.AUTHENTICATED,
                self._identity(
                    matches[0],
                    "DEMO_ONLY_PHONE_MATCH",
                ),
                calling_code_from_phone(normalized),
            )
        else:
            result = CallerIdentityResult(
                (
                    CallerIdentityStatus.AMBIGUOUS
                    if matches
                    else CallerIdentityStatus.NEEDS_DOCUMENT
                ),
                country_code=calling_code_from_phone(normalized),
            )

        _telemetry(
            "caller_identity.phone_lookup",
            status=result.status.value,
            match_count=len(matches),
            duration_ms=round(
                (time.perf_counter() - started) * 1000,
                2,
            ),
        )

        return result

    def identify_document(
        self,
        document_number: str,
    ) -> CallerIdentityResult:
        started = time.perf_counter()
        normalized = normalize_document(document_number)

        if not normalized:
            result = CallerIdentityResult(CallerIdentityStatus.NOT_FOUND)

            _telemetry(
                "caller_identity.document_lookup",
                status=result.status.value,
                match_count=0,
                duration_ms=round(
                    (time.perf_counter() - started) * 1000,
                    2,
                ),
            )

            return result

        if self.customer_repository is not None:
            customer = self.customer_repository.get_by_document(normalized)
            matches = (
                (customer,)
                if customer is not None and customer.customer_status.casefold() == "active"
                else ()
            )
            result = CallerIdentityResult(
                CallerIdentityStatus.AUTHENTICATED if matches else CallerIdentityStatus.NOT_FOUND,
                (
                    self._identity_from_customer(customer, "DEMO_ONLY_DOCUMENT_MATCH")
                    if matches
                    else None
                ),
            )
            _telemetry(
                "caller_identity.document_lookup",
                status=result.status.value,
                match_count=len(matches),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return result

        matches = self._document_index.get(
            normalized,
            (),
        )

        if len(matches) == 1:
            result = CallerIdentityResult(
                CallerIdentityStatus.AUTHENTICATED,
                self._identity(
                    matches[0],
                    "DEMO_ONLY_DOCUMENT_MATCH",
                ),
            )
        else:
            result = CallerIdentityResult(
                CallerIdentityStatus.AMBIGUOUS if matches else CallerIdentityStatus.NOT_FOUND
            )

        _telemetry(
            "caller_identity.document_lookup",
            status=result.status.value,
            match_count=len(matches),
            duration_ms=round(
                (time.perf_counter() - started) * 1000,
                2,
            ),
        )

        return result

    @staticmethod
    def _identity(
        record: _CallerRecord,
        assurance: str,
    ) -> CallerIdentity:
        return CallerIdentity(
            customer_id=record.customer_id,
            first_name=record.first_name,
            last_name=record.last_name,
            full_name=record.full_name,
            gender=None,
            age=None,
            country=record.country,
            detected_accent=record.detected_accent,
            preferred_locale=record.preferred_locale,
            assurance_level=assurance,
        )

    @staticmethod
    def _identity_from_customer(
        customer: Customer,
        assurance: str,
    ) -> CallerIdentity:
        today = date.today()
        born = customer.date_of_birth
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return CallerIdentity(
            customer_id=customer.customer_id,
            first_name=customer.first_name,
            last_name=customer.last_name,
            full_name=f"{customer.first_name} {customer.last_name}",
            gender=customer.gender.value,
            age=age,
            country=customer.country,
            detected_accent=customer.detected_accent.value,
            preferred_locale=customer.interface_locale.value,
            assurance_level=assurance,
        )
