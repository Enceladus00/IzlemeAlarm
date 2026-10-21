CREATE TABLE customer (
    customer_id BIGSERIAL PRIMARY KEY,
    customer_no VARCHAR(20) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    customer_type VARCHAR(10),
    occupation VARCHAR(50),
    monthly_income NUMERIC(18,2),
    risk_level VARCHAR(6),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE account (
    account_id BIGSERIAL PRIMARY KEY,
    account_no VARCHAR(34) UNIQUE NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customer(customer_id),
    currency CHAR(3) NOT NULL,
    account_type VARCHAR(10),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    opened_at DATE
);

CREATE TABLE "transaction" (
    transaction_id BIGSERIAL PRIMARY KEY,
    transaction_no VARCHAR(30) UNIQUE NOT NULL,
    sender_account_id BIGINT NOT NULL REFERENCES account(account_id),
    receiver_account_id BIGINT NOT NULL REFERENCES account(account_id),
    amount NUMERIC(18,2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    tx_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    channel VARCHAR(10) NOT NULL
        CHECK (channel IN ('atm', 'mobile', 'internet', 'branch')),
    country_code CHAR(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    loaded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE app_user (
    user_id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'analyst', 'auditor')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE monitoring_rule (
    rule_id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    thresholds JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by BIGINT REFERENCES app_user(user_id)
);

CREATE TABLE rule_change_log (
    change_id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT NOT NULL REFERENCES monitoring_rule(rule_id),
    changed_by BIGINT NOT NULL REFERENCES app_user(user_id),
    old_thresholds JSONB NOT NULL,
    new_thresholds JSONB NOT NULL,
    changed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE upload_batch (
    batch_id BIGSERIAL PRIMARY KEY,
    uploaded_by BIGINT NOT NULL REFERENCES app_user(user_id),
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('customer', 'account', 'transaction')),
    file_name TEXT NOT NULL,
    total_rows INTEGER NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
    accepted_rows INTEGER NOT NULL DEFAULT 0 CHECK (accepted_rows >= 0),
    rejected_rows INTEGER NOT NULL DEFAULT 0 CHECK (rejected_rows >= 0),
    uploaded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE upload_row_error (
    row_error_id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES upload_batch(batch_id),
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    reason TEXT NOT NULL,
    row_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE alert (
    alert_id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT NOT NULL REFERENCES monitoring_rule(rule_id),
    customer_id BIGINT NOT NULL REFERENCES customer(customer_id),
    severity VARCHAR(10) NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    status VARCHAR(30) NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'in_review', 'closed', 'confirmed_suspicious')),
    deduplication_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE alert_transaction (
    alert_id BIGINT NOT NULL REFERENCES alert(alert_id),
    transaction_id BIGINT NOT NULL REFERENCES "transaction"(transaction_id),
    PRIMARY KEY (alert_id, transaction_id)
);

CREATE TABLE alert_status_history (
    history_id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES alert(alert_id),
    changed_by BIGINT NOT NULL REFERENCES app_user(user_id),
    old_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL
        CHECK (new_status IN ('new', 'in_review', 'closed', 'confirmed_suspicious')),
    note TEXT,
    changed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (new_status NOT IN ('closed', 'confirmed_suspicious') OR
           NULLIF(BTRIM(note), '') IS NOT NULL)
);

CREATE TABLE audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    actor_id BIGINT REFERENCES app_user(user_id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_account_customer_id ON account(customer_id);
CREATE INDEX idx_transaction_sender_time ON "transaction"(sender_account_id, tx_time);
CREATE INDEX idx_transaction_receiver_time ON "transaction"(receiver_account_id, tx_time);
CREATE INDEX idx_alert_status_created_at ON alert(status, created_at DESC);
CREATE INDEX idx_alert_customer_id ON alert(customer_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX idx_upload_row_error_batch_id ON upload_row_error(batch_id);

CREATE FUNCTION reject_immutable_record_changes() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Records in % are append-only', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER alert_status_history_is_append_only
    BEFORE UPDATE OR DELETE ON alert_status_history
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_changes();
CREATE TRIGGER audit_log_is_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_changes();
CREATE TRIGGER rule_change_log_is_append_only
    BEFORE UPDATE OR DELETE ON rule_change_log
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_record_changes();

INSERT INTO monitoring_rule (rule_code, name, description, thresholds) VALUES
    ('R1', 'Threshold-adjacent repeated transactions',
     'Detects repeated transactions just below a configured limit within a short time window.',
     '{"amount_limit": 10000, "proximity_percent": 10, "transaction_count": 2, "window_minutes": 60}'::jsonb),
    ('R2', 'Rapid in-and-out transfers',
     'Detects a large proportion of incoming funds transferred out within a short time window.',
     '{"outflow_ratio": 0.8, "window_minutes": 60}'::jsonb),
    ('R3', 'Unusual transaction amount',
     'Detects transactions significantly above the customer''s historical average.',
     '{"average_multiplier": 3, "minimum_history_count": 5}'::jsonb),
    ('R4', 'Risky country',
     'Optionally detects transactions associated with configured high-risk countries.',
     '{"countries": [], "enabled": false}'::jsonb)
ON CONFLICT (rule_code) DO NOTHING;
