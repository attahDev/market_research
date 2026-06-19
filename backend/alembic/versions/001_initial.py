from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "market_research"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "research_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("query_normalized", sa.Text(), nullable=False),
        sa.Column("category", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(10), nullable=False, server_default="fresh"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column("plan_tier", sa.String(20), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_research_jobs_query_normalized",
        "research_jobs",
        ["query_normalized"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_research_jobs_status", "research_jobs", ["status"], schema=SCHEMA
    )
    op.create_index(
        "ix_research_jobs_expires_at", "research_jobs", ["expires_at"], schema=SCHEMA
    )

    op.create_table(
        "research_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.research_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("query_normalized", sa.Text(), nullable=False),
        sa.Column("balance", sa.Text(), nullable=False),
        sa.Column("trend_summary", sa.Text(), nullable=False),
        sa.Column("insights", postgresql.JSONB(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("classifier_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("classifier_source", sa.String(10), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_research_results_query_normalized",
        "research_results",
        ["query_normalized"],
        schema=SCHEMA,
    )

    op.create_table(
        "usage_tracking",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("query_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.UniqueConstraint("user_id", "month", name="uq_usage_tracking_user_month"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("usage_tracking", schema=SCHEMA)
    op.drop_table("research_results", schema=SCHEMA)
    op.drop_table("research_jobs", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
