from datetime import date, datetime

from pydantic import BaseModel


class CallCenterInteraction(BaseModel):
    interaction_id: str
    interaction_date: datetime
    process_date: date
    customer_id: str
    agent_id: str | None = None
    interaction_type: str
    channel: str
    contact_reason: str
    reason_category: str
    duration_seconds: int | None = None
    wait_time_seconds: int | None = None
    was_resolved: bool | None = None
    requires_followup: bool
    detected_sentiment: str | None = None
    sentiment_score: float | None = None
    customer_detected_accent: str | None = None
    agent_used_accent: str | None = None
    was_escalated: bool
    mentioned_products: str | None = None
    has_transcript: bool
    has_recording: bool
