from pydantic import BaseModel, ConfigDict, Field


class StoreProductResponse(BaseModel):
    product_id: str
    name: str
    tagline: str
    description: str
    category: str
    price: float
    currency: str
    emoji: str
    badge: str | None


class CheckoutItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=10)


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_product_id: str = Field(min_length=1, max_length=100)
    items: list[CheckoutItemRequest] = Field(min_length=1, max_length=20)


class CheckoutResponse(BaseModel):
    order_id: str
    transaction_id: str
    item_count: int
    total: float
    currency: str
    message: str
