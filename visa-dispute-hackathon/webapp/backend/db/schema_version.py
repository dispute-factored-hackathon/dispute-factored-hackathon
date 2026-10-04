"""Schema revision required by the runtime.

Keep this constant in sync when adding an Alembic migration. Runtime processes import this tiny
module instead of importing Alembic and SQLAlchemy during every cold start.
"""

LATEST_SCHEMA_REVISION = "0002"
