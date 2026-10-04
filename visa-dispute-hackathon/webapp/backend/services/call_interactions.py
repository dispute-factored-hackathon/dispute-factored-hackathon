"""Persist the live, synthetic SIP interaction without giving the model write authority."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from webapp.backend.models.call_center_interaction import CallCenterInteraction
from webapp.backend.models.call_transcript import CallTranscript
from webapp.backend.models.satisfaction_survey import SatisfactionSurvey
from webapp.backend.repositories.interfaces import (
    CallCenterInteractionRepository,
    CallTranscriptRepository,
    SatisfactionSurveyRepository,
    ServiceAgentRepository,
)
from webapp.backend.services.izzy_agent import IZZY_AGENT_ID, seed_izzy_agent


@dataclass(frozen=True)
class InteractionChannel:
    """How an Izzy conversation is recorded in the call-center tables."""

    interaction_type: str
    channel: str
    survey_channel: str
    main_topics: str


PHONE_CHANNEL = InteractionChannel(
    interaction_type="Inbound Call",
    channel="Phone",
    survey_channel="Phone",
    main_topics="Authentication, transaction search, Visa dispute",
)
WEB_CHAT_CHANNEL = InteractionChannel(
    interaction_type="Web Chat",
    channel="Web Chat",
    survey_channel="Web Chat",
    main_topics="Transaction search, Visa dispute",
)


def _id(prefix: str, call_id: str) -> str:
    return f"{prefix}-{hashlib.sha256(call_id.encode()).hexdigest()[:20]}"


class CallInteractionService:
    """Own interaction/transcript/CSAT writes and their deterministic identifiers."""

    def __init__(
        self,
        agents: ServiceAgentRepository,
        interactions: CallCenterInteractionRepository,
        transcripts: CallTranscriptRepository,
        surveys: SatisfactionSurveyRepository,
        *,
        transcription_model: str,
        channel: InteractionChannel = PHONE_CHANNEL,
    ) -> None:
        self.channel = channel
        self.agents = agents
        self.interactions = interactions
        self.transcripts = transcripts
        self.surveys = surveys
        self.transcription_model = transcription_model
        self._started: dict[str, datetime] = {}
        self._turns: dict[str, list[tuple[str, str]]] = {}
        seed_izzy_agent(agents)

    def start(self, call_id: str) -> None:
        self._started.setdefault(call_id, datetime.now(UTC))
        self._turns.setdefault(call_id, [])

    @staticmethod
    def interaction_id(call_id: str) -> str:
        return _id("INT", call_id)

    def record_turn(self, state: Any, speaker: Literal["customer", "agent"], text: str) -> None:
        cleaned = " ".join(text.split())
        if not cleaned:
            return
        self.start(state.call_id)
        self._turns[state.call_id].append((speaker, cleaned))
        if state.identity is not None:
            self._ensure_interaction(state)
            self._write_transcript(state)
            self.sync(state)

    def sync(self, state: Any) -> None:
        """Create after authentication, then update after every validated state change."""

        if state.identity is None:
            return
        interaction = self._ensure_interaction(state)
        classification = state.dispute_classification
        transaction = state.confirmed_transaction or state.current_transaction
        code = classification.visa_condition_code if classification else None
        contact_reason = "Card dispute support"
        if code:
            contact_reason = f"Visa dispute {code}"
        resolved = True if state.complaint_id else None
        escalated = str(state.stage) == "handoff"
        updated = interaction.model_copy(
            update={
                "contact_reason": contact_reason,
                "duration_seconds": self._duration(state.call_id),
                "was_resolved": resolved,
                "requires_followup": not bool(state.complaint_id),
                "customer_detected_accent": state.locale.accent,
                "agent_used_accent": state.locale.accent,
                "was_escalated": escalated,
                "mentioned_products": transaction.product_id if transaction else None,
                "has_transcript": bool(self._turns.get(state.call_id)),
            }
        )
        self.interactions.update(updated)
        if self._turns.get(state.call_id):
            self._write_transcript(state)

    def record_csat(self, state: Any, rating: int) -> SatisfactionSurvey:
        if not 1 <= rating <= 5:
            raise ValueError("CSAT rating must be between 1 and 5.")
        if state.identity is None:
            raise ValueError("CSAT requires an authenticated customer.")
        interaction = self._ensure_interaction(state)
        existing = self.surveys.get_by_interaction(interaction.interaction_id)
        if existing is not None:
            return existing
        sentiment, score = {
            1: ("Very Negative", -1.0),
            2: ("Negative", -0.5),
            3: ("Neutral", 0.0),
            4: ("Positive", 0.5),
            5: ("Very Positive", 1.0),
        }[rating]
        now = datetime.now(UTC)
        survey = self.surveys.create(
            SatisfactionSurvey(
                survey_id=_id("SRV", state.call_id),
                survey_date=now,
                process_date=now.date(),
                interaction_id=interaction.interaction_id,
                customer_id=state.identity.customer_id,
                agent_id=IZZY_AGENT_ID,
                survey_type="CSAT",
                send_channel=self.channel.survey_channel,
                main_score=rating,
                question_1_text="How would you rate this service from 1 to 5?",
                question_1_response=rating,
                comment_sentiment=sentiment,
                response_time_hours=0.0,
            )
        )
        self.interactions.update(
            interaction.model_copy(
                update={"detected_sentiment": sentiment, "sentiment_score": score}
            )
        )
        ratings = self.surveys.list_by_agent(IZZY_AGENT_ID)
        agent = self.agents.get_by_id(IZZY_AGENT_ID)
        assert agent is not None
        self.agents.update(
            agent.model_copy(
                update={
                    "avg_csat": round(sum(item.main_score for item in ratings) / len(ratings), 2)
                }
            )
        )
        return survey

    def finalize(self, state: Any) -> None:
        if state.identity is None:
            return
        self.sync(state)
        interaction = self.interactions.get_by_id(_id("INT", state.call_id))
        if interaction is not None and interaction.was_resolved is None:
            self.interactions.update(
                interaction.model_copy(
                    update={
                        "duration_seconds": self._duration(state.call_id),
                        "requires_followup": True,
                        "was_escalated": interaction.was_escalated or str(state.stage) == "handoff",
                    }
                )
            )

    def _ensure_interaction(self, state: Any) -> CallCenterInteraction:
        interaction_id = _id("INT", state.call_id)
        existing = self.interactions.get_by_id(interaction_id)
        if existing is not None:
            return existing
        self.start(state.call_id)
        now = self._started[state.call_id]
        interaction = self.interactions.create(
            CallCenterInteraction(
                interaction_id=interaction_id,
                interaction_date=now,
                process_date=now.date(),
                customer_id=state.identity.customer_id,
                agent_id=IZZY_AGENT_ID,
                interaction_type=self.channel.interaction_type,
                channel=self.channel.channel,
                contact_reason="Card dispute support",
                reason_category="Complaint",
                duration_seconds=0,
                wait_time_seconds=0,
                was_resolved=None,
                requires_followup=True,
                customer_detected_accent=state.locale.accent,
                agent_used_accent=state.locale.accent,
                was_escalated=False,
                has_transcript=False,
                has_recording=False,
            )
        )
        agent = self.agents.get_by_id(IZZY_AGENT_ID)
        assert agent is not None
        self.agents.update(
            agent.model_copy(
                update={"total_monthly_interactions": (agent.total_monthly_interactions or 0) + 1}
            )
        )
        return interaction

    def _write_transcript(self, state: Any) -> CallTranscript:
        interaction = self._ensure_interaction(state)
        turns = self._turns[state.call_id]
        customer_text = "\n".join(text for speaker, text in turns if speaker == "customer") or None
        agent_text = "\n".join(text for speaker, text in turns if speaker == "agent") or None
        full_text = "\n".join(f"{speaker.title()}: {text}" for speaker, text in turns)
        transcript = CallTranscript(
            transcript_id=_id("TRN", state.call_id),
            interaction_id=interaction.interaction_id,
            process_date=datetime.now(UTC).date(),
            customer_id=state.identity.customer_id,
            agent_id=IZZY_AGENT_ID,
            full_text=full_text,
            customer_text=customer_text,
            agent_text=agent_text,
            detected_language=state.locale.language,
            detected_accent=state.locale.accent,
            accent_confidence=1.0,
            detected_intents="Card dispute",
            main_topics=self.channel.main_topics,
            transcription_model=self.transcription_model,
            audio_quality="Unknown",
            duration_seconds=self._duration(state.call_id),
        )
        existing = self.transcripts.get_by_interaction(interaction.interaction_id)
        return (
            self.transcripts.update(transcript) if existing else self.transcripts.create(transcript)
        )

    def _duration(self, call_id: str) -> int:
        started = self._started.get(call_id, datetime.now(UTC))
        return max(0, int((datetime.now(UTC) - started).total_seconds()))
