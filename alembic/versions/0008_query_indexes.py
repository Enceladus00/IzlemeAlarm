"""Indexes for columns that hot queries filter or join on.

Before this migration these lookups scanned the whole table:
* alert_status_history by alert (alert queue, funnel, history) and by actor
  (my_summary),
* alert_transaction by transaction (the primary key starts with alert_id),
* audit_log by entity (alert events, R17 "already raised" check),
* alert by rule + customer + status (open-alert lookup during detection),
* rule_result by rule + customer (alert explanation; the unique key starts
  with run_id).
Mirrored in database/V7__query_indexes.sql.
"""

from alembic import op


revision = "0008_query_indexes"
down_revision = "0007_admin_all_permissions"
branch_labels = None
depends_on = None

INDEXES = (
    ("idx_alert_status_history_alert_changed", "alert_status_history", ["alert_id", "changed_at"]),
    ("idx_alert_status_history_changed_by", "alert_status_history", ["changed_by", "changed_at"]),
    ("idx_alert_transaction_transaction_id", "alert_transaction", ["transaction_id"]),
    ("idx_audit_log_entity", "audit_log", ["entity_type", "entity_id"]),
    ("idx_alert_rule_customer_status", "alert", ["rule_id", "customer_id", "status"]),
    ("idx_rule_result_rule_customer", "rule_result", ["rule_id", "customer_id"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
