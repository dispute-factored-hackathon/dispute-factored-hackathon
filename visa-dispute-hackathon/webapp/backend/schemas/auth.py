from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    factored_id: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
    )


class AuthenticatedCustomerResponse(BaseModel):
    customer_id: str
    first_name: str
    last_name: str
    factored_id: str
    preferred_accent: str
    onboarding_completed: bool


class LoginResponse(BaseModel):
    authenticated: bool
    customer: AuthenticatedCustomerResponse


class LogoutResponse(BaseModel):
    authenticated: bool
