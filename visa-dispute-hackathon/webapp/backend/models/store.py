from pydantic import BaseModel


class StoreProduct(BaseModel):
    product_id: str
    name: str
    tagline: str
    description: str
    category: str
    price: float
    currency: str = "USD"
    emoji: str
    badge: str | None = None


class StoreCartItem(BaseModel):
    product_id: str
    quantity: int
