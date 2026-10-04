import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from webapp.backend.api.dependencies import require_customer
from webapp.backend.config import get_settings
from webapp.backend.models.customer import Customer
from webapp.backend.schemas.izzy import (
    IzzyChatEntry,
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


async def get_izzy_chat(request: Request) -> Any:
    """Load the chat stack on first use, independently from ordinary bank pages."""

    from webapp.backend.services.runtime import ensure_izzy_chat

    return await ensure_izzy_chat(request.app)


IzzyChatDependency = Annotated[Any, Depends(get_izzy_chat)]


def _format_phone(e164: str) -> str:
    digits = e164.lstrip("+")
    if e164.startswith("+1") and len(digits) == 11:
        return f"+1 {digits[1:4]} {digits[4:7]} {digits[7:]}"
    return e164


@router.get("/contact", response_model=IzzyContactResponse)
def contact() -> IzzyContactResponse:
    phone_number = get_settings().izzy_phone_number
    return IzzyContactResponse(phone_number=phone_number, phone_display=_format_phone(phone_number))


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
        messages=[IzzyChatEntry(**entry) for entry in opening.messages],
        resumed=opening.resumed,
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
    except LookupError as error:
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
        except LookupError:
            yield _sse({"event": "error", "text": "Chat session not found. Start a new chat."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
