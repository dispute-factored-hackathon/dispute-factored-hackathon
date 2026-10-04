"""Lazy application services for fast serverless page delivery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI

from webapp.backend.config import get_settings
from webapp.backend.repositories.interfaces import Repositories


def _open_repositories() -> Repositories:
    """Import PostgreSQL and migration dependencies only when an API actually needs data."""

    from webapp.backend.repositories.postgres import open_repositories

    return open_repositories(get_settings())


@asynccontextmanager
async def application_runtime(app: FastAPI) -> AsyncIterator[None]:
    """Prepare lightweight locks; database and AI services remain lazy."""

    app.state.repositories = None
    app.state.izzy_chat = None
    app.state.repositories_lock = asyncio.Lock()
    app.state.izzy_chat_lock = asyncio.Lock()
    async with AsyncExitStack() as stack:
        app.state.service_stack = stack
        try:
            yield
        finally:
            repositories = app.state.repositories
            if repositories is not None:
                repositories.close()
            for name in (
                "service_stack",
                "izzy_chat_lock",
                "repositories_lock",
                "izzy_chat",
                "repositories",
            ):
                delattr(app.state, name)


async def ensure_repositories(app: FastAPI) -> Repositories:
    """Open the shared PostgreSQL pool once, on the first data-backed API request."""

    repositories = app.state.repositories
    if repositories is not None:
        return repositories
    async with app.state.repositories_lock:
        repositories = app.state.repositories
        if repositories is None:
            repositories = await asyncio.to_thread(_open_repositories)
            app.state.repositories = repositories
    return repositories


async def ensure_izzy_chat(app: FastAPI) -> Any:
    """Load LangGraph/OpenAI and connect its checkpointer only when chat is opened."""

    chat = app.state.izzy_chat
    if chat is not None:
        return chat
    async with app.state.izzy_chat_lock:
        chat = app.state.izzy_chat
        if chat is None:
            from dispute_agent.web_chat import build_izzy_web_chat
            from dispute_agent.web_chat.checkpoint import open_chat_checkpointer

            repositories = await ensure_repositories(app)
            settings = get_settings()
            checkpointer = await open_chat_checkpointer(settings, app.state.service_stack)
            chat = build_izzy_web_chat(repositories, settings, checkpointer=checkpointer)
            app.state.izzy_chat = chat
    return chat
