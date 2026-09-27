"""Minimal GUI entrypoint for the synthetic dispute demo."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Cookie, FastAPI, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .gui_session import DemoLoginError, GuiDemoLoginService

DEFAULT_CUSTOMERS = Path(__file__).parents[2] / "data" / "raw" / "customers.csv"
LOGIN_PAGE = Path(__file__).with_name("static") / "login.html"


class SelectionRequest(BaseModel):
    selection_token: str


def create_app(customers_csv: str | Path | None = None) -> FastAPI:
    """Create the GUI app with one server-owned synthetic login service."""

    selected_csv = customers_csv or os.getenv("CUSTOMERS_CSV", str(DEFAULT_CUSTOMERS))
    login = GuiDemoLoginService(selected_csv)
    app = FastAPI(title="Bank Factored dispute demo")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return LOGIN_PAGE.read_text(encoding="utf-8")

    @app.get("/api/customers")
    def search_customers(
        query: str = Query(default="", max_length=login.MAX_QUERY_CHARACTERS),
        limit: int = Query(default=10, ge=1, le=20),
    ) -> dict[str, object]:
        return {
            "options": [
                {
                    "selection_token": option.selection_token,
                    "display_name": option.display_name,
                    "disambiguation": option.disambiguation,
                }
                for option in login.search(query, limit=limit)
            ]
        }

    @app.post("/api/session", status_code=201)
    def create_session(payload: SelectionRequest, response: Response) -> dict[str, object]:
        try:
            context = login.select(payload.selection_token)
        except DemoLoginError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        response.set_cookie(
            "demo_session",
            context.session_id,
            httponly=True,
            samesite="lax",
            max_age=int(login.session_ttl.total_seconds()),
        )
        return {
            "display_name": context.display_name,
            "country": context.country,
            "assurance_level": context.assurance_level,
            "demo_only": True,
        }

    @app.get("/api/session")
    def read_session(demo_session: str | None = Cookie(default=None)) -> dict[str, object]:
        if not demo_session:
            raise HTTPException(status_code=401, detail="demo session is required")
        try:
            context = login.resolve_session(demo_session)
        except DemoLoginError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        return {
            "display_name": context.display_name,
            "country": context.country,
            "assurance_level": context.assurance_level,
            "demo_only": True,
        }

    @app.delete("/api/session", status_code=204)
    def delete_session(response: Response, demo_session: str | None = Cookie(default=None)) -> None:
        if demo_session:
            login.logout(demo_session)
        response.delete_cookie("demo_session")

    app.state.demo_login = login
    return app


def run() -> None:
    """Run the local GUI demo."""

    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
