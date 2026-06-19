
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "002_confidence_scores"
down_revision = "001_initial"
branch_labels = None
depends_on = None

SCHEMA = "market_research"


def upgrade() -> None:
    op.add_column("research_results",
        sa.Column("data_confidence", sa.Numeric(4, 3), nullable=True),
        schema=SCHEMA)
    op.add_column("research_results",
        sa.Column("fetched_at", sa.String(40), nullable=True),
        schema=SCHEMA)

    op.add_column("research_results",
        sa.Column("opportunities", JSONB, nullable=False, server_default="[]"),
        schema=SCHEMA)
    op.add_column("research_results",
        sa.Column("risks", JSONB, nullable=False, server_default="[]"),
        schema=SCHEMA)
    op.add_column("research_results",
        sa.Column("recommendations", JSONB, nullable=False, server_default="[]"),
        schema=SCHEMA)


def downgrade() -> None:
    for col in ["data_confidence", "fetched_at", "opportunities", "risks", "recommendations"]:
        op.drop_column("research_results", col, schema=SCHEMA)
