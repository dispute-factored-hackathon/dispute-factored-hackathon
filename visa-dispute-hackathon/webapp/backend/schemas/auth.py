from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    factored_id: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
    )


class DemoLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection: str = Field(min_length=20, max_length=500)


class DemoLoginOption(BaseModel):
    selection: str
    full_name: str
    disambiguator: str


class DemoLoginOptionsResponse(BaseModel):
    options: list[DemoLoginOption]


class AuthenticatedCustomerResponse(BaseModel):
    customer_id: str
    first_name: str
    last_name: str
    factored_id: str
    preferred_accent: str
    locale: str
    onboarding_completed: bool
    onboarding_eligible: bool


class LoginResponse(BaseModel):
    authenticated: bool
    customer: AuthenticatedCustomerResponse


class LogoutResponse(BaseModel):
    authenticated: bool
