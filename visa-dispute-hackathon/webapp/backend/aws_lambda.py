"""AWS Lambda adapter for the FastAPI web application."""

import asyncio
from typing import Any

from mangum import Mangum

from webapp.backend.aws_runtime import configure_application_runtime

_adapter: Mangum | None = None


def _get_adapter() -> Mangum:
    global _adapter
    if _adapter is None:
        configure_application_runtime()
        # Settings and the FastAPI app must only be imported after secrets configure the process.
        from webapp.backend.main import app

        _adapter = Mangum(app, lifespan="auto")
    return _adapter


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Serve a Function URL event, restoring the loop if prior code closed it."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    return _get_adapter()(event, context)
