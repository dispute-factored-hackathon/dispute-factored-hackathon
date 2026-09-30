from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from webapp.backend.api.routes.auth import (
    router as auth_router,
)
from webapp.backend.api.routes.customers import (
    router as customers_router,
)
from webapp.backend.api.routes.products import (
    router as products_router,
)
from webapp.backend.api.routes.transactions import (
    router as transactions_router,
)
from webapp.backend.config import get_settings

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
PAGES_DIR = FRONTEND_DIR / "pages"


app = FastAPI(
    title=settings.app_name,
)

app.include_router(auth_router)
app.include_router(customers_router)
app.include_router(products_router)
app.include_router(transactions_router)


app.mount(
    "/static",
    StaticFiles(
        directory=FRONTEND_DIR,
    ),
    name="static",
)


def page(filename: str) -> FileResponse:
    return FileResponse(PAGES_DIR / filename)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
    }


@app.get("/")
def index() -> FileResponse:
    return page("login.html")


@app.get("/login")
def login_page() -> FileResponse:
    return page("login.html")


@app.get("/signup")
def signup_page() -> FileResponse:
    return page("signup.html")


@app.get("/home")
def home_page() -> FileResponse:
    return page("home.html")


@app.get("/cards")
def cards_page() -> FileResponse:
    return page("cards.html")


@app.get("/transactions")
def transactions_page() -> FileResponse:
    return page("transactions.html")


@app.get("/transactions/{transaction_id}")
def transaction_detail_page(
    transaction_id: str,
) -> FileResponse:
    del transaction_id

    return page("transaction-detail.html")


@app.get("/complaints")
def complaints_page() -> FileResponse:
    return page("coming-soon.html")


@app.get("/profile")
def profile_page() -> FileResponse:
    return page("coming-soon.html")


@app.get("/agent")
def agent_page() -> FileResponse:
    return page("coming-soon.html")


@app.get("/shop")
def shop_page() -> FileResponse:
    return page("coming-soon.html")
