"""AWS Lambda adapter for the FastAPI web application."""

import asyncio
from typing import Any

from mangum import Mangum

from webapp.backend.main import app

# Repositories and demo data are process-scoped in the hackathon build. Keeping
# ASGI lifespan handling off avoids closing them after every Lambda invocation.
_adapter = Mangum(app, lifespan="off")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Serve a Function URL event, restoring the loop if prior code closed it."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    return _adapter(event, context)
