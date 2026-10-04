"""Izzy web chat: the voice dispute workflow, entered from an authenticated web session."""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver

from webapp.backend.config import Settings
from webapp.backend.repositories.card_purchases import CombinedCardPurchaseRepository
from webapp.backend.repositories.interfaces import Repositories

from ..jev_decision import JevVoiceRouter
from .graph import ChatOpening, ChatSessionNotFoundError, IzzyChatGraph, IzzyWebChat
from .interpreter import ChatTurnInterpreter
from .service import WebChatDisputeService


def build_izzy_web_chat(
    repositories: Repositories,
    settings: Settings,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
) -> IzzyWebChat:
    """Wire the chat to the shared PostgreSQL repositories (called by the app lifespan)."""

    openai_api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    jev_api_key = settings.jev_api_key.get_secret_value() if settings.jev_api_key else None
    # Card purchases from the lakehouse (seeded history) and PostgreSQL (live activity).
    purchases = CombinedCardPurchaseRepository.from_settings(repositories.card_purchases, settings)
    return IzzyWebChat(
        WebChatDisputeService.from_repositories(repositories, purchases=purchases),
        ChatTurnInterpreter(
            jev_router=JevVoiceRouter(api_key=jev_api_key),
            openai_api_key=openai_api_key,
            model=settings.openai_agent_model,
        ),
        phone_number=settings.izzy_phone_number,
        openai_api_key=openai_api_key,
        model=settings.openai_agent_model,
        checkpointer=checkpointer,
        session_ttl_seconds=settings.izzy_chat_session_ttl_minutes * 60,
        max_message_chars=settings.izzy_chat_max_message_chars,
        max_turns=settings.izzy_chat_max_turns,
    )


__all__ = [
    "ChatOpening",
    "ChatSessionNotFoundError",
    "ChatTurnInterpreter",
    "IzzyChatGraph",
    "IzzyWebChat",
    "WebChatDisputeService",
    "build_izzy_web_chat",
]
