"""Card-purchase search for the Izzy web chat: up to three selectable options.

The web chat searches the authenticated customer's card purchases (lakehouse + PostgreSQL, see
`webapp.backend.repositories.card_purchases`) with the same explainable ranking as calls, plus the
purchase category. Instead of reading one candidate aloud, it offers at most three options; an
obvious single match is offered alone. The ranking runs only on records already scoped to the
customer, so another customer's purchase can never become an option.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, replace
from typing import Any

from webapp.backend.models.card_transaction import CardTransaction
from webapp.backend.repositories.interfaces import CardPurchaseRepository

from ..transaction_search import (
    MIN_RELEVANCE_SCORE,
    InsufficientTransactionCriteriaError,
    TransactionSearchCriteria,
    _rank_transaction,
)

_DATE_WORDS = frozenset(
    {
        # relative days and periods
        "today", "yesterday", "week", "weekend", "month", "year", "ago",
        "hoy", "ayer", "anteayer", "semana", "mes", "ano", "hace", "pasado", "pasada",
        "hoje", "ontem", "anteontem", "passado", "passada",
        # weekdays
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
        "segunda", "terca", "quarta", "quinta", "sexta",
        # months
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
        "septiembre", "setiembre", "octubre", "noviembre", "diciembre",
        "janeiro", "fevereiro", "marco", "maio", "junho", "julho", "setembro",
        "outubro", "novembro", "dezembro",
    }
)  # fmt: skip
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_NUMERIC_DATE = re.compile(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b")


def typed_date_evidence(message: str) -> bool:
    """True when the customer actually wrote a date or period.

    Typed chat is stricter than speech about numbers but looser about dates: a year ("in 2025")
    or a relative period ("yesterday", "last month") is enough, while dates the model invents
    from text with no date at all are still dropped.
    """

    decomposed = unicodedata.normalize("NFKD", message.casefold())
    text = "".join(character for character in decomposed if not unicodedata.combining(character))
    if _YEAR.search(text) or _NUMERIC_DATE.search(text):
        return True
    return bool(set(re.findall(r"[a-z]+", text)) & _DATE_WORDS)


MAX_OPTIONS = 3
# A single option is offered when the best match clearly beats the runner-up.
CLEAR_WINNER_SCORE = 0.85
CLEAR_WINNER_MARGIN = 0.25


@dataclass(frozen=True)
class CardPurchaseCriteria(TransactionSearchCriteria):
    """The voice search filters plus the purchase category (web chat only)."""

    category: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> CardPurchaseCriteria:
        base = TransactionSearchCriteria.from_mapping(values)
        category = values.get("category")
        normalized = " ".join(str(category).split()) if category is not None else ""
        if len(normalized) > 80:
            raise ValueError("category is too long")
        return cls.upgrade(base, category=normalized or None)

    @classmethod
    def upgrade(
        cls, criteria: TransactionSearchCriteria, *, category: str | None = None
    ) -> CardPurchaseCriteria:
        if isinstance(criteria, cls) and category is None:
            return criteria
        values = {
            field.name: getattr(criteria, field.name) for field in fields(TransactionSearchCriteria)
        }
        current = criteria.category if isinstance(criteria, cls) else None
        return cls(**values, category=category if category is not None else current)

    def without(self, field_names: Iterable[str]) -> CardPurchaseCriteria:
        requested = tuple(field_names)
        kept = super().without(name for name in requested if name != "category")
        if "category" in requested:
            kept = replace(kept, category=None)
        return kept

    @property
    def is_discriminative(self) -> bool:
        return super().is_discriminative or bool(self.category)

    def web_filters(self) -> dict[str, str]:
        """Active filters for the chat (voice templates never see the category)."""

        active = {name: str(value) for name, value in self.active_filters()}
        if self.category:
            active["category"] = self.category
        return active


@dataclass(frozen=True)
class PurchaseOption:
    purchase: CardTransaction
    score: float
    matched_fields: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        return option_payload(self.purchase)


def option_payload(purchase: CardTransaction) -> dict[str, Any]:
    """What the chat UI and the reply model may show about one option."""

    transaction = purchase.transaction
    return {
        "transaction_id": transaction.transaction_id,
        "merchant": transaction.merchant_name,
        "date": transaction.transaction_date.isoformat(),
        "amount": transaction.amount,
        "currency": transaction.currency,
        "city": transaction.transaction_city,
        "country": transaction.transaction_country,
        "category": transaction.transaction_category,
        "channel": transaction.channel,
        "card_type": purchase.card_type,
        "card_last_four": purchase.card_last_four,
    }


class CardPurchaseSearch:
    """Rank the customer's card purchases and return at most three options."""

    def __init__(self, purchases: CardPurchaseRepository) -> None:
        self.purchases = purchases

    def search(
        self,
        customer_id: str,
        criteria: CardPurchaseCriteria,
        *,
        excluded_transaction_ids: Iterable[str] = (),
    ) -> list[PurchaseOption]:
        if not customer_id.strip():
            raise ValueError("customer_id is required")
        if not criteria.is_discriminative:
            raise InsufficientTransactionCriteriaError(
                "provide merchant, amount, date, category, or location"
            )
        excluded = set(excluded_transaction_ids)
        ranked = sorted(
            (
                PurchaseOption(purchase, ranking.score, ranking.matched_fields)
                for purchase in self.purchases.list_by_customer(customer_id)
                if purchase.transaction.customer_id == customer_id
                and purchase.transaction.transaction_id not in excluded
                for ranking in (_rank_transaction(purchase.transaction, criteria),)
            ),
            key=lambda option: (option.score, option.purchase.transaction.transaction_date),
            reverse=True,
        )
        relevant = [option for option in ranked if option.score >= MIN_RELEVANCE_SCORE]
        if (
            len(relevant) >= 2
            and relevant[0].score >= CLEAR_WINNER_SCORE
            and relevant[0].score - relevant[1].score >= CLEAR_WINNER_MARGIN
        ):
            return relevant[:1]
        return relevant[:MAX_OPTIONS]
