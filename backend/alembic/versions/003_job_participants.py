from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "003_job_participants"
down_revision = "002_confidence_scores"
branch_labels = None
depends_on = None

SCHEMA = "market_research"


def upgrade() -> None:
    op.create_table(
        "research_job_participants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.research_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reference_id", sa.String(64), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False, server_default="original"),
        sa.Column("settled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("job_id", "reference_id", name="uq_job_participant_reference"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_research_job_participants_job_id",
        "research_job_participants",
        ["job_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_research_job_participants_settled",
        "research_job_participants",
        ["settled"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_research_job_participants_settled", table_name="research_job_participants", schema=SCHEMA)
    op.drop_index("ix_research_job_participants_job_id", table_name="research_job_participants", schema=SCHEMA)
    op.drop_table("research_job_participants", schema=SCHEMA)
