from datetime import date, datetime

from pydantic import BaseModel


class SatisfactionSurvey(BaseModel):
    survey_id: str
    survey_date: datetime
    process_date: date
    interaction_id: str | None = None
    customer_id: str
    agent_id: str | None = None
    survey_type: str
    send_channel: str
    main_score: int
    nps_category: str | None = None
    question_1_text: str | None = None
    question_1_response: int | None = None
    question_2_text: str | None = None
    question_2_response: int | None = None
    question_3_text: str | None = None
    question_3_response: int | None = None
    open_comments: str | None = None
    comment_sentiment: str | None = None
    response_time_hours: float | None = None
    campaign_response_rate: float | None = None
