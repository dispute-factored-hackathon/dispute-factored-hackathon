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
from webapp.backend.config import get_settings

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"


app = FastAPI(
    title=settings.app_name,
)

app.include_router(auth_router)
app.include_router(customers_router)


app.mount(
    "/static",
    StaticFiles(
        directory=FRONTEND_DIR,
    ),
    name="static",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "pages" / "login.html")


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "pages" / "login.html")


@app.get("/signup")
def signup_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "pages" / "signup.html")


@app.get("/home")
def home_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "pages" / "home.html")
