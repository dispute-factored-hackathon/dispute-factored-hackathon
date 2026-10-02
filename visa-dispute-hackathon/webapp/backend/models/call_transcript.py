from datetime import date

from pydantic import BaseModel


class CallTranscript(BaseModel):
    transcript_id: str
    interaction_id: str
    process_date: date
    customer_id: str
    agent_id: str
    full_text: str
    customer_text: str | None = None
    agent_text: str | None = None
    detected_language: str
    detected_accent: str | None = None
    accent_confidence: float | None = None
    detected_keywords: str | None = None
    mentioned_entities: str | None = None
    detected_intents: str | None = None
    main_topics: str | None = None
    transcription_model: str
    audio_quality: str | None = None
    duration_seconds: int
