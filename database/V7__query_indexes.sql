-- Indexes for columns that hot queries filter or join on.
-- Mirrors alembic/versions/0008_query_indexes.py.

CREATE INDEX IF NOT EXISTS idx_alert_status_history_alert_changed
    ON alert_status_history(alert_id, changed_at);
CREATE INDEX IF NOT EXISTS idx_alert_status_history_changed_by
    ON alert_status_history(changed_by, changed_at);
CREATE INDEX IF NOT EXISTS idx_alert_transaction_transaction_id
    ON alert_transaction(transaction_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity
    ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_alert_rule_customer_status
    ON alert(rule_id, customer_id, status);
CREATE INDEX IF NOT EXISTS idx_rule_result_rule_customer
    ON rule_result(rule_id, customer_id);
