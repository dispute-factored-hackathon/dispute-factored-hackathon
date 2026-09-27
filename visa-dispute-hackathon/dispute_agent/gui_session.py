"""Searchable synthetic GUI login and server-side session state."""

from __future__ import annotations

import csv
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .authentication import normalize_name
from .language_context import ConversationLocaleContext


class DemoLoginError(ValueError):
    """Raised when a GUI selection or session cannot be trusted."""


@dataclass(frozen=True)
class CustomerOption:
    """Safe customer information that a searchable dropdown may display."""

    selection_token: str
    display_name: str
    disambiguation: str | None = None


@dataclass(frozen=True)
class AuthenticatedCustomerContext:
    """Authoritative server-side context produced by the demo login."""

    session_id: str
    customer_id: str
    display_name: str
    country: str | None
    language: ConversationLocaleContext
    assurance_level: str
    expires_at: datetime


@dataclass(frozen=True)
class _CustomerRecord:
    customer_id: str
    display_name: str
    search_text: str
    country: str | None
    city: str | None
    preferred_language: str | None
    locale: str | None


@dataclass(frozen=True)
class _PendingSelection:
    customer_id: str
    expires_at: datetime


class GuiDemoLoginService:
    """Issue opaque dropdown selections and short-lived synthetic sessions.

    The service deliberately models a hackathon login, not production bank
    authentication. Customer IDs never need to be accepted from the browser.
    """

    MAX_QUERY_CHARACTERS = 120

    def __init__(
        self,
        customers_csv: str | Path,
        *,
        selection_ttl: timedelta = timedelta(minutes=5),
        session_ttl: timedelta = timedelta(hours=1),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.customers_csv = Path(customers_csv)
        self.selection_ttl = selection_ttl
        self.session_ttl = session_ttl
        self._now = now or (lambda: datetime.now(UTC))
        self._records = self._load_records()
        self._records_by_id = {record.customer_id: record for record in self._records}
        self._pending: dict[str, _PendingSelection] = {}
        self._sessions: dict[str, AuthenticatedCustomerContext] = {}

    def _load_records(self) -> tuple[_CustomerRecord, ...]:
        if not self.customers_csv.is_file():
            raise FileNotFoundError(f"Customers CSV not found: {self.customers_csv}")
        records: list[_CustomerRecord] = []
        with self.customers_csv.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"customer_id", "first_name", "last_name"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"Customers CSV is missing columns: {sorted(missing)}")
            for row in reader:
                if row.get("customer_status", "Active").strip().casefold() != "active":
                    continue
                display_name = " ".join((row["first_name"].strip(), row["last_name"].strip()))
                records.append(
                    _CustomerRecord(
                        customer_id=row["customer_id"].strip(),
                        display_name=display_name,
                        search_text=normalize_name(display_name),
                        country=(row.get("country") or "").strip() or None,
                        city=(row.get("city") or "").strip() or None,
                        preferred_language=(row.get("preferred_language") or "").strip() or None,
                        locale=(row.get("locale") or "").strip() or None,
                    )
                )
        return tuple(records)

    def search(self, query: str = "", *, limit: int = 10) -> list[CustomerOption]:
        """Return safe dropdown options; each opaque token requires selection."""

        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if len(query) > self.MAX_QUERY_CHARACTERS:
            raise ValueError("query is too long")
        normalized_query = normalize_name(query)
        matches = [
            record
            for record in self._records
            if not normalized_query or normalized_query in record.search_text
        ][:limit]
        counts: dict[str, int] = {}
        for record in matches:
            counts[record.search_text] = counts.get(record.search_text, 0) + 1

        now = self._now()
        self._discard_expired(now)
        options: list[CustomerOption] = []
        for record in matches:
            token = secrets.token_urlsafe(24)
            self._pending[token] = _PendingSelection(
                customer_id=record.customer_id,
                expires_at=now + self.selection_ttl,
            )
            location = " · ".join(value for value in (record.country, record.city) if value)
            disambiguation = location or "Synthetic customer"
            if counts[record.search_text] == 1:
                disambiguation = record.country
            options.append(
                CustomerOption(
                    selection_token=token,
                    display_name=record.display_name,
                    disambiguation=disambiguation,
                )
            )
        return options

    def select(self, selection_token: str) -> AuthenticatedCustomerContext:
        """Create a session only from a live server-issued dropdown option."""

        now = self._now()
        self._discard_expired(now)
        pending = self._pending.pop(selection_token, None)
        if pending is None:
            raise DemoLoginError("selection is missing, expired, already used, or invalid")
        record = self._records_by_id.get(pending.customer_id)
        if record is None:
            raise DemoLoginError("selected customer is no longer available")
        session_id = secrets.token_urlsafe(32)
        context = AuthenticatedCustomerContext(
            session_id=session_id,
            customer_id=record.customer_id,
            display_name=record.display_name,
            country=record.country,
            language=ConversationLocaleContext.from_gui_record(
                country=record.country,
                preferred_language=record.preferred_language,
                locale=record.locale,
            ),
            assurance_level="DEMO_GUI_CUSTOMER_SELECTED",
            expires_at=now + self.session_ttl,
        )
        self._sessions[session_id] = context
        return context

    def resolve_session(self, session_id: str) -> AuthenticatedCustomerContext:
        """Return the server-side customer context for a live session."""

        now = self._now()
        self._discard_expired(now)
        context = self._sessions.get(session_id)
        if context is None:
            raise DemoLoginError("session is missing, expired, logged out, or invalid")
        return context

    def logout(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _discard_expired(self, now: datetime) -> None:
        self._pending = {
            token: pending for token, pending in self._pending.items() if pending.expires_at > now
        }
        self._sessions = {
            session_id: context
            for session_id, context in self._sessions.items()
            if context.expires_at > now
        }
