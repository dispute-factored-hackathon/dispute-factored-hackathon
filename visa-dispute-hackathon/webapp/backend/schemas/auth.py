from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    factored_id: str = Field(
        pattern=r"^\d{6}$",
    )


class AuthenticatedCustomerResponse(BaseModel):
    customer_id: str
    first_name: str
    last_name: str
    preferred_accent: str


class LoginResponse(BaseModel):
    authenticated: bool
    customer: AuthenticatedCustomerResponse


class LogoutResponse(BaseModel):
    authenticated: bool
