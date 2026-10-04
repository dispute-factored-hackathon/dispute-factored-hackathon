"""AWS Lambda adapter for the FastAPI web application.

Mangum normally enters and exits FastAPI's lifespan for every Lambda invocation.  That is a poor
fit for Izzy: opening a chat and sending its first message are separate HTTP requests, while the
live workflow registry intentionally belongs to the warm Lambda environment.  Keep one lifespan
open for that environment and let AWS dispose of it with the process.  Durable LangGraph
checkpoints still live in PostgreSQL; this only prevents normal consecutive requests from looking
like an expired chat.
"""

import asyncio
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import FastAPI
from mangum import Mangum

from webapp.backend.aws_runtime import configure_application_runtime

_adapter: Mangum | None = None
_lifespan: AbstractAsyncContextManager[Any] | None = None
_loop: asyncio.AbstractEventLoop | None = None
_application: FastAPI | None = None


def _event_loop() -> asyncio.AbstractEventLoop:
    """Return the Lambda environment's reusable event loop."""

    global _loop
    if _loop is not None and not _loop.is_closed():
        return _loop
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _get_adapter() -> Mangum:
    global _adapter, _application, _lifespan
    if _adapter is None:
        configure_application_runtime()
        # Settings and the FastAPI app must only be imported after secrets configure the process.
        from webapp.backend.main import app

        _application = app
        # Enter once per warm Lambda environment. Mangum's per-invocation lifespan would tear
        # down Izzy's in-memory workflow registry between POST /sessions and POST /messages.
        _lifespan = app.router.lifespan_context(app)
        _event_loop().run_until_complete(_lifespan.__aenter__())
        _adapter = Mangum(app, lifespan="off")
    return _adapter


def _warm_application() -> dict[str, bool]:
    """Initialize database and web chat in the current environment for the scheduled demo ping."""

    _get_adapter()
    assert _application is not None
    from webapp.backend.services.runtime import ensure_izzy_chat

    _event_loop().run_until_complete(ensure_izzy_chat(_application))
    return {"warmed": True}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Serve a Function URL event, restoring the loop if prior code closed it."""
    _event_loop()
    if event.get("warmup") is True:
        return _warm_application()
    return _get_adapter()(event, context)
