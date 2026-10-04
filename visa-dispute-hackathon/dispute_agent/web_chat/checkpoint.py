"""Where the Izzy web chat keeps its LangGraph checkpoints: PostgreSQL, the app's database.

`dispute-db-migrate` creates the checkpoint tables with the owner role; the app role can only read
and write rows. If PostgreSQL cannot be used asynchronously (for example uvicorn's default
Proactor event loop on Windows, which psycopg does not support), the chat keeps working with
in-memory checkpoints and logs how to fix it.
"""

from __future__ import annotations

import json
import logging
from contextlib import AsyncExitStack

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from webapp.backend.config import Settings

LOGGER = logging.getLogger(__name__)


async def open_chat_checkpointer(settings: Settings, stack: AsyncExitStack) -> BaseCheckpointSaver:
    if settings.database_url is None:
        return InMemorySaver()
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        saver = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(settings.database_url.get_secret_value())
        )
        # Fails fast if the tables are missing or the event loop cannot run async psycopg.
        await saver.aget_tuple({"configurable": {"thread_id": "startup-check"}})
    except Exception as error:
        LOGGER.warning(
            json.dumps(
                {
                    "event": "web_chat.checkpointer.in_memory",
                    "error_type": type(error).__name__,
                    "hint": (
                        "Run `uv run dispute-db-migrate`; on Windows start uvicorn with "
                        "`--loop asyncio:SelectorEventLoop`."
                    ),
                }
            )
        )
        return InMemorySaver()
    LOGGER.info(json.dumps({"event": "web_chat.checkpointer.postgres"}))
    return saver
