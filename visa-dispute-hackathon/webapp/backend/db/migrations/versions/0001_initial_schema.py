"""Initial transactional schema for the Factored Bank demo.

Mirrors webapp/backend/models (customers, products, transactions, complaints) plus a
hashed-session table. Synthetic data only.

Revision ID: 0001
Revises:
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TIMESTAMPTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "customers",
        sa.Column("customer_id", sa.Text, primary_key=True),
        sa.Column("document_number", sa.Text, nullable=False),
        sa.Column("document_type", sa.Text, nullable=False),
        sa.Column("first_name", sa.Text, nullable=False),
        sa.Column("last_name", sa.Text, nullable=False),
        # Lower-cased, accent-free "first last", maintained by the repository for fast search.
        sa.Column("search_name", sa.Text, nullable=False),
        sa.Column("date_of_birth", sa.Date, nullable=False),
        sa.Column("gender", sa.Text, nullable=False),
        sa.Column("mobile_phone", sa.Text),
        sa.Column("city", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("country", sa.Text, nullable=False),
        sa.Column("detected_accent", sa.Text, nullable=False),
        sa.Column("segment", sa.Text, nullable=False),
        sa.Column("registration_date", TIMESTAMPTZ, nullable=False),
        sa.Column("registration_branch_id", sa.Integer, nullable=False),
        sa.Column("customer_status", sa.Text, nullable=False),
        sa.Column("preferred_locale", sa.Text),
        sa.Column("onboarding_completed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("tutorial_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tutorial_status", sa.Text, nullable=False, server_default="not_started"),
        sa.Column("tutorial_last_completed_step", sa.Text),
        sa.Column("last_updated", TIMESTAMPTZ, nullable=False),
        sa.UniqueConstraint("document_number", name="customers_document_number_key"),
    )
    # Several customers may have no phone; only real numbers must be unique.
    op.create_index(
        "customers_mobile_phone_key",
        "customers",
        ["mobile_phone"],
        unique=True,
        postgresql_where=sa.text("mobile_phone IS NOT NULL"),
    )
    op.create_index(
        "customers_search_name_trgm",
        "customers",
        ["search_name"],
        postgresql_using="gin",
        postgresql_ops={"search_name": "gin_trgm_ops"},
    )
    op.create_index("customers_search_name_order", "customers", ["search_name", "customer_id"])

    op.create_table(
        "products",
        sa.Column("product_id", sa.Text, primary_key=True),
        sa.Column("customer_id", sa.Text, sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("product_type", sa.Text, nullable=False),
        # Synthetic card number. The web layer only ever returns the last four digits.
        sa.Column("product_number", sa.Text, nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("current_balance", sa.Numeric(15, 2), nullable=False),
        sa.Column("credit_limit", sa.Numeric(15, 2), nullable=False),
        sa.Column("opening_date", sa.Date, nullable=False),
        sa.Column("opening_branch_id", sa.Integer, nullable=False),
        sa.Column("product_status", sa.Text, nullable=False),
        sa.Column("opening_channel", sa.Text, nullable=False),
        sa.Column("has_linked_app", sa.Boolean, nullable=False),
        sa.Column("last_updated", TIMESTAMPTZ, nullable=False),
    )
    op.create_index("products_customer_id", "products", ["customer_id"])

    op.create_table(
        "transactions",
        sa.Column("transaction_id", sa.Text, primary_key=True),
        sa.Column("transaction_date", TIMESTAMPTZ, nullable=False),
        sa.Column("process_date", sa.Date, nullable=False),
        sa.Column("product_id", sa.Text, sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("customer_id", sa.Text, sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("transaction_type", sa.Text, nullable=False),
        sa.Column("transaction_category", sa.Text),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("amount_usd", sa.Numeric(15, 2)),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("branch_id", sa.Text),
        sa.Column("merchant_name", sa.Text),
        sa.Column("merchant_category", sa.Text),
        sa.Column("transaction_country", sa.Text, nullable=False),
        sa.Column("transaction_city", sa.Text),
        sa.Column("transaction_status", sa.Text, nullable=False),
        sa.Column("response_code", sa.Text),
        sa.Column("is_fraud", sa.Boolean, nullable=False),
        sa.Column("fraud_score", sa.Numeric(6, 4)),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
    )
    op.create_index(
        "transactions_customer_date",
        "transactions",
        ["customer_id", sa.text("transaction_date DESC")],
    )
    op.create_index("transactions_product_id", "transactions", ["product_id"])

    op.create_table(
        "complaints",
        sa.Column("complaint_id", sa.Text, primary_key=True),
        sa.Column("creation_date", TIMESTAMPTZ, nullable=False),
        sa.Column("process_date", sa.Date, nullable=False),
        sa.Column("customer_id", sa.Text, sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("case_type", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("subcategory", sa.Text),
        sa.Column("reception_channel", sa.Text, nullable=False),
        # No foreign key: a complaint may reference a product that is not a card.
        sa.Column("affected_product_id", sa.Text),
        sa.Column("related_branch_id", sa.Text),
        sa.Column("origin_interaction_id", sa.Text),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("claimed_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("priority", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("assigned_agent_id", sa.Text),
        sa.Column("assignment_date", TIMESTAMPTZ),
        sa.Column("first_response_date", TIMESTAMPTZ),
        sa.Column("resolution_date", TIMESTAMPTZ),
        sa.Column("closing_date", TIMESTAMPTZ),
        sa.Column("sla_breached", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("resolution_days", sa.Integer),
        sa.Column("resolution", sa.Text),
        sa.Column("compensation_granted", sa.Numeric(15, 2)),
        sa.Column("resolution_satisfaction", sa.Numeric(4, 2)),
        sa.Column("is_repeat_complainer", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "complaints_customer_date",
        "complaints",
        ["customer_id", sa.text("creation_date DESC")],
    )

    # Only the SHA-256 of the session id is stored, so a leaked table cannot be replayed as cookies.
    op.create_table(
        "sessions",
        sa.Column("session_hash", sa.CHAR(64), primary_key=True),
        sa.Column(
            "customer_id",
            sa.Text,
            sa.ForeignKey("customers.customer_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("authentication_method", sa.Text, nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.Column("expires_at", TIMESTAMPTZ, nullable=False),
    )
    op.create_index("sessions_expires_at", "sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("complaints")
    op.drop_table("transactions")
    op.drop_table("products")
    op.drop_table("customers")
    # pg_trgm is left installed: it may be shared with other schemas.
