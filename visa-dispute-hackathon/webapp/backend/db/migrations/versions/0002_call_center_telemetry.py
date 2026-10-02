"""Call-center agents, interactions, live transcripts, and CSAT.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02
"""

from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TIMESTAMPTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "service_agents",
        sa.Column("agent_id", sa.Text, primary_key=True),
        sa.Column("employee_code", sa.Text, nullable=False, unique=True),
        sa.Column("first_name", sa.Text, nullable=False),
        sa.Column("last_name", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("phone", sa.Text),
        sa.Column("native_accent", sa.Text, nullable=False),
        sa.Column("country_of_origin", sa.Text, nullable=False),
        sa.Column("assigned_branch_id", sa.Text),
        sa.Column("agent_type", sa.Text, nullable=False),
        sa.Column("experience_level", sa.Text, nullable=False),
        sa.Column("languages", sa.Text, nullable=False),
        sa.Column("specialty", sa.Text),
        sa.Column("hire_date", sa.Date, nullable=False),
        sa.Column("avg_csat", sa.Numeric(3, 2)),
        sa.Column("total_monthly_interactions", sa.Integer),
        sa.Column("agent_status", sa.Text, nullable=False),
        sa.Column("work_shift", sa.Text, nullable=False),
    )
    service_agents = sa.table(
        "service_agents",
        *(
            sa.column(name)
            for name in (
                "agent_id",
                "employee_code",
                "first_name",
                "last_name",
                "email",
                "phone",
                "native_accent",
                "country_of_origin",
                "assigned_branch_id",
                "agent_type",
                "experience_level",
                "languages",
                "specialty",
                "hire_date",
                "avg_csat",
                "total_monthly_interactions",
                "agent_status",
                "work_shift",
            )
        ),
    )
    op.bulk_insert(
        service_agents,
        [
            {
                "agent_id": "AGENT-IZZY",
                "employee_code": "IZZY-AI-001",
                "first_name": "Izzy",
                "last_name": "Factored",
                "email": "izzy@factored.demo",
                "phone": None,
                "native_accent": "Multilingual",
                "country_of_origin": "Synthetic",
                "assigned_branch_id": None,
                "agent_type": "Hybrid",
                "experience_level": "Specialist",
                "languages": "English, Portuguese, Spanish",
                "specialty": "Card Disputes",
                "hire_date": date(2026, 1, 1),
                "avg_csat": None,
                "total_monthly_interactions": 0,
                "agent_status": "Active",
                "work_shift": "Always-on",
            }
        ],
    )
    op.create_table(
        "call_center_interactions",
        sa.Column("interaction_id", sa.Text, primary_key=True),
        sa.Column("interaction_date", TIMESTAMPTZ, nullable=False),
        sa.Column("process_date", sa.Date, nullable=False),
        sa.Column("customer_id", sa.Text, sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("agent_id", sa.Text, sa.ForeignKey("service_agents.agent_id")),
        sa.Column("interaction_type", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("contact_reason", sa.Text, nullable=False),
        sa.Column("reason_category", sa.Text, nullable=False),
        sa.Column("duration_seconds", sa.Integer),
        sa.Column("wait_time_seconds", sa.Integer),
        sa.Column("was_resolved", sa.Boolean),
        sa.Column("requires_followup", sa.Boolean, nullable=False),
        sa.Column("detected_sentiment", sa.Text),
        sa.Column("sentiment_score", sa.Numeric(4, 3)),
        sa.Column("customer_detected_accent", sa.Text),
        sa.Column("agent_used_accent", sa.Text),
        sa.Column("was_escalated", sa.Boolean, nullable=False),
        sa.Column("mentioned_products", sa.Text),
        sa.Column("has_transcript", sa.Boolean, nullable=False),
        sa.Column("has_recording", sa.Boolean, nullable=False),
    )
    op.create_index(
        "call_center_interactions_customer_date",
        "call_center_interactions",
        ["customer_id", sa.text("interaction_date DESC")],
    )
    op.create_table(
        "call_transcripts",
        sa.Column("transcript_id", sa.Text, primary_key=True),
        sa.Column(
            "interaction_id",
            sa.Text,
            sa.ForeignKey("call_center_interactions.interaction_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("process_date", sa.Date, nullable=False),
        sa.Column("customer_id", sa.Text, sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("agent_id", sa.Text, sa.ForeignKey("service_agents.agent_id"), nullable=False),
        sa.Column("full_text", sa.Text, nullable=False),
        sa.Column("customer_text", sa.Text),
        sa.Column("agent_text", sa.Text),
        sa.Column("detected_language", sa.Text, nullable=False),
        sa.Column("detected_accent", sa.Text),
        sa.Column("accent_confidence", sa.Numeric(5, 4)),
        sa.Column("detected_keywords", sa.Text),
        sa.Column("mentioned_entities", sa.Text),
        sa.Column("detected_intents", sa.Text),
        sa.Column("main_topics", sa.Text),
        sa.Column("transcription_model", sa.Text, nullable=False),
        sa.Column("audio_quality", sa.Text),
        sa.Column("duration_seconds", sa.Integer, nullable=False),
    )
    op.create_table(
        "satisfaction_surveys",
        sa.Column("survey_id", sa.Text, primary_key=True),
        sa.Column("survey_date", TIMESTAMPTZ, nullable=False),
        sa.Column("process_date", sa.Date, nullable=False),
        sa.Column(
            "interaction_id",
            sa.Text,
            sa.ForeignKey("call_center_interactions.interaction_id"),
            unique=True,
        ),
        sa.Column("customer_id", sa.Text, sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("agent_id", sa.Text, sa.ForeignKey("service_agents.agent_id")),
        sa.Column("survey_type", sa.Text, nullable=False),
        sa.Column("send_channel", sa.Text, nullable=False),
        sa.Column("main_score", sa.Integer, nullable=False),
        sa.Column("nps_category", sa.Text),
        sa.Column("question_1_text", sa.Text),
        sa.Column("question_1_response", sa.Integer),
        sa.Column("question_2_text", sa.Text),
        sa.Column("question_2_response", sa.Integer),
        sa.Column("question_3_text", sa.Text),
        sa.Column("question_3_response", sa.Integer),
        sa.Column("open_comments", sa.Text),
        sa.Column("comment_sentiment", sa.Text),
        sa.Column("response_time_hours", sa.Float),
        sa.Column("campaign_response_rate", sa.Float),
    )


def downgrade() -> None:
    op.drop_table("satisfaction_surveys")
    op.drop_table("call_transcripts")
    op.drop_table("call_center_interactions")
    op.drop_table("service_agents")
