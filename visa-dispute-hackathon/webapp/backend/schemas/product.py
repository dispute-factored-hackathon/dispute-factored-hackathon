from pydantic import BaseModel


class ProductResponse(BaseModel):
    product_id: str
    product_type: str
    masked_number: str
    last_four: str
    currency: str
    product_status: str


class ProductStatusResponse(BaseModel):
    product_id: str
    product_status: str
