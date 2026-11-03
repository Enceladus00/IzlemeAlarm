from alembic import op
import sqlalchemy as sa


revision = "0005_system_overview_metrics"
down_revision = "0004_extended_detection_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.alter_column(
        "account",
        "created_at",
        existing_type=sa.DateTime(),
        existing_nullable=True,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    op.add_column(
        "detection_run",
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("detection_run", "duration_ms")
    op.drop_column("account", "created_at")
