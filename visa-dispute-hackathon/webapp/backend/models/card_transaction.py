from pydantic import BaseModel

from webapp.backend.models.transaction import Transaction

# Card products and the transaction type that the dispute agents consider ("relevant card
# purchases"). Labels are the app's normalised forms; the lakehouse stores them in capitals.
CARD_PRODUCT_TYPES = ("Credit Card", "Debit Card")
CARD_PURCHASE_TYPE = "Purchase"


class CardTransaction(BaseModel):
    """A card purchase with the card it was charged to (never the full card number)."""

    transaction: Transaction
    card_type: str
    card_last_four: str
    card_status: str
    source: str  # "postgres" or "lakehouse"
