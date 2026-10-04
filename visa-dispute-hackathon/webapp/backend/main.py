from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from dispute_agent.web_chat import build_izzy_web_chat
from dispute_agent.web_chat.checkpoint import open_chat_checkpointer
from webapp.backend.api.dependencies import (
    SESSION_COOKIE_NAME,
    AuthenticationServiceDependency,
)
from webapp.backend.api.routes.auth import (
    router as auth_router,
)
from webapp.backend.api.routes.complaints import (
    router as complaints_router,
)
from webapp.backend.api.routes.customers import (
    router as customers_router,
)
from webapp.backend.api.routes.izzy import router as izzy_router
from webapp.backend.api.routes.localization import (
    router as localization_router,
)
from webapp.backend.api.routes.onboarding import (
    router as onboarding_router,
)
from webapp.backend.api.routes.products import (
    router as products_router,
)
from webapp.backend.api.routes.store import router as store_router
from webapp.backend.api.routes.transactions import (
    router as transactions_router,
)
from webapp.backend.config import get_settings
from webapp.backend.repositories.postgres import open_repositories

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
PAGES_DIR = FRONTEND_DIR / "pages"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # PostgreSQL is the only data store; customer data comes from `dispute-db-seed-lakehouse`.
    repositories = open_repositories(settings)
    app.state.repositories = repositories
    try:
        async with AsyncExitStack() as stack:
            # Izzy web chat: the voice dispute workflow over the same repositories, with its
            # conversation checkpoints in the same PostgreSQL.
            checkpointer = await open_chat_checkpointer(settings, stack)
            app.state.izzy_chat = build_izzy_web_chat(
                repositories, settings, checkpointer=checkpointer
            )
            try:
                yield
            finally:
                del app.state.izzy_chat
    finally:
        del app.state.repositories
        repositories.close()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)


app.include_router(auth_router)
app.include_router(localization_router)
app.include_router(customers_router)
app.include_router(products_router)
app.include_router(transactions_router)
app.include_router(complaints_router)
app.include_router(onboarding_router)
app.include_router(store_router)
app.include_router(izzy_router)


app.mount(
    "/static",
    StaticFiles(
        directory=FRONTEND_DIR,
    ),
    name="static",
)


def page(
    filename: str,
) -> FileResponse:
    # Pages are small HTML shells: always revalidate so a browser never keeps an outdated page
    # (for example the old "coming soon" placeholder at /agent?intent=new_complaint).
    return FileResponse(PAGES_DIR / filename, headers={"Cache-Control": "no-cache"})


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
    return page("complaints.html")


@app.get("/complaints/{complaint_id}")
def complaint_detail_page(
    complaint_id: str,
) -> FileResponse:
    del complaint_id

    return page("complaint-detail.html")


@app.get("/profile")
def profile_page() -> FileResponse:
    return page("profile.html")


@app.get("/agent")
def agent_page() -> FileResponse:
    return page("agent.html")


@app.get("/shop")
def shop_page() -> FileResponse:
    return page("store.html")


@app.get("/shop/products/{product_id}")
def shop_product_page(product_id: str) -> FileResponse:
    del product_id
    return page("store-product.html")


@app.get("/shop/cart")
def shop_cart_page() -> FileResponse:
    return page("store-cart.html")


@app.api_route(
    "/{unknown_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def redirect_unknown_page(
    unknown_path: str,
    request: Request,
    authentication_service: AuthenticationServiceDependency,
) -> RedirectResponse:
    if request.method != "GET" or unknown_path == "api" or unknown_path.startswith("api/"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )

    if unknown_path.startswith("shop/"):
        return RedirectResponse(url="/shop", status_code=status.HTTP_303_SEE_OTHER)

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    destination = (
        "/home" if session_id and authentication_service.authenticate(session_id) else "/login"
    )
    return RedirectResponse(url=destination, status_code=status.HTTP_303_SEE_OTHER)
