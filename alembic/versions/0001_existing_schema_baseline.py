from pathlib import Path

from alembic import op
from sqlalchemy import inspect, text


revision = "0001_existing_schema_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    required = {
        "customer",
        "account",
        "transaction",
        "app_user",
        "monitoring_rule",
        "rule_change_log",
        "upload_batch",
        "upload_row_error",
        "alert",
        "alert_transaction",
        "alert_status_history",
        "audit_log",
    }
    if existing & required:
        missing = required - existing
        if missing:
            raise RuntimeError(
                "Existing database has a partial project schema; missing tables: "
                + ", ".join(sorted(missing))
            )
    else:
        schema_file = Path(__file__).resolve().parents[2] / "database" / "V1__initial_schema.sql"
        bind.exec_driver_sql(schema_file.read_text(encoding="utf-8"))
    bind.execute(
        text(
            "INSERT INTO app_user (username, password_hash, role) "
            "VALUES ('demo-system', 'not-a-login-account', 'analyst') "
            "ON CONFLICT (username) DO NOTHING"
        )
    )


def downgrade() -> None:
    raise RuntimeError(
        "The baseline represents existing user data and cannot be downgraded safely."
    )
