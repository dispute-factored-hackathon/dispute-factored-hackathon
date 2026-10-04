import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from dispute_agent.web_chat import ChatSessionNotFoundError, IzzyWebChat
from dispute_agent.web_chat.replies import format_phone
from webapp.backend.api.dependencies import require_customer
from webapp.backend.config import get_settings
from webapp.backend.models.customer import Customer
from webapp.backend.schemas.izzy import (
    IzzyContactResponse,
    IzzyMessageRequest,
    IzzyPurchaseOption,
    IzzySessionRequest,
    IzzySessionResponse,
)

router = APIRouter(
    prefix="/api/izzy",
    tags=["izzy"],
)


def get_izzy_chat(request: Request) -> IzzyWebChat:
    """The chat opened by the application lifespan (see `main.py`)."""

    chat = getattr(request.app.state, "izzy_chat", None)
    if chat is None:
        raise RuntimeError("The Izzy chat was not opened at application startup.")
    return chat


IzzyChatDependency = Annotated[IzzyWebChat, Depends(get_izzy_chat)]


@router.get("/contact", response_model=IzzyContactResponse)
def contact() -> IzzyContactResponse:
    phone_number = get_settings().izzy_phone_number
    return IzzyContactResponse(phone_number=phone_number, phone_display=format_phone(phone_number))


@router.post(
    "/sessions",
    response_model=IzzySessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def open_session(
    request: IzzySessionRequest,
    customer: Annotated[Customer, Depends(require_customer)],
    chat: IzzyChatDependency,
) -> IzzySessionResponse:
    opening = chat.open_session(
        customer,
        locale=request.locale,
        transaction_id=request.transaction_id,
    )
    return IzzySessionResponse(
        session_id=opening.session_id,
        message=opening.message,
        stage=opening.stage,
        language=opening.language,
        transaction_context=opening.transaction_context,
        options=[IzzyPurchaseOption(**option) for option in opening.options],
        selected_transaction_id=opening.selected_transaction_id,
        phone_number=chat.phone_number,
        phone_display=chat.phone_display,
    )


def _sse(event: dict[str, Any]) -> str:
    name = event["event"]
    payload = {key: value for key, value in event.items() if key != "event"}
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: str,
    request: IzzyMessageRequest,
    customer: Annotated[Customer, Depends(require_customer)],
    chat: IzzyChatDependency,
) -> StreamingResponse:
    try:
        chat.ensure_owned(session_id, customer.customer_id)
    except ChatSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found. Start a new chat.",
        ) from error

    async def events() -> AsyncIterator[str]:
        try:
            async for event in chat.stream_turn(
                session_id,
                customer.customer_id,
                request.message,
                selected_transaction_id=request.selected_transaction_id,
                reject_options=request.reject_options,
            ):
                yield _sse(event)
        except ChatSessionNotFoundError:
            yield _sse({"event": "error", "text": "Chat session not found. Start a new chat."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
