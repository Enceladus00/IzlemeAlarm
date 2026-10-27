ALTER TABLE monitoring_rule
    ADD COLUMN weight NUMERIC(4,3) NOT NULL DEFAULT 1.000;
ALTER TABLE monitoring_rule
    ADD CONSTRAINT ck_monitoring_rule_weight_range
    CHECK (weight >= 0 AND weight <= 1);
ALTER TABLE alert
    ADD COLUMN score NUMERIC(5,4);
ALTER TABLE alert
    ADD CONSTRAINT ck_alert_score_range
    CHECK (score IS NULL OR (score >= 0 AND score <= 1));

CREATE TABLE detection_run (
    run_id UUID PRIMARY KEY,
    as_of TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_detection_run_status
        CHECK (status IN ('running', 'completed', 'failed'))
);

CREATE TABLE rule_result (
    result_id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES detection_run(run_id),
    rule_id BIGINT NOT NULL REFERENCES monitoring_rule(rule_id),
    customer_id BIGINT NOT NULL REFERENCES customer(customer_id),
    customer_type VARCHAR(10),
    weight_snapshot NUMERIC(4,3) NOT NULL,
    parameter_snapshot JSONB NOT NULL,
    parameter_status VARCHAR(20) NOT NULL,
    result_status VARCHAR(30) NOT NULL,
    raw_x NUMERIC(18,6),
    score NUMERIC(5,4),
    alert_mode VARCHAR(20) NOT NULL,
    step_trace JSONB NOT NULL,
    CONSTRAINT uq_rule_result_run_rule_customer
        UNIQUE (run_id, rule_id, customer_id),
    CONSTRAINT ck_rule_result_parameter_status
        CHECK (parameter_status IN ('UNSET', 'PROVISIONAL', 'APPROVED')),
    CONSTRAINT ck_rule_result_result_status
        CHECK (result_status IN ('evaluated', 'skipped_unset', 'skipped_customer_type')),
    CONSTRAINT ck_rule_result_score_range
        CHECK (score IS NULL OR (score >= 0 AND score <= 1)),
    CONSTRAINT ck_rule_result_weight_range
        CHECK (weight_snapshot >= 0 AND weight_snapshot <= 1)
);

CREATE TABLE rule_result_transaction (
    result_id BIGINT NOT NULL REFERENCES rule_result(result_id),
    transaction_id BIGINT NOT NULL REFERENCES "transaction"(transaction_id),
    PRIMARY KEY (result_id, transaction_id)
);

INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
SELECT NULL, 'rule.migrated_inactive', 'monitoring_rule', rule_code,
       jsonb_build_object('old_is_active', is_active, 'new_is_active', FALSE)
FROM monitoring_rule
WHERE rule_code IN ('R1', 'R2', 'R3', 'R4') AND is_active = TRUE;

UPDATE monitoring_rule
SET is_active = FALSE
WHERE rule_code IN ('R1', 'R2', 'R3', 'R4');

INSERT INTO monitoring_rule
    (rule_code, name, description, is_active, weight, thresholds)
VALUES
    ('R01', 'Bölme - Limitin hemen altında birden çok işlem',
     'Son 7 günde limitin hemen altındaki işlemleri, üst limit ve gelire göre değerlendirir.',
     FALSE, 1.000,
     '{"BIREYSEL":{"status":"UNSET","values":{}},'
     '"KURUMSAL":{"status":"UNSET","values":{}}}'::jsonb),
    ('R02', 'Büyük tek işlem - Limiti aşan işlem (büyüklük sinyali)',
     'Müşteri tipi ve para birimi limitini aşan işlemi INFO sinyali olarak kaydeder.',
     FALSE, 0.450,
     '{"BIREYSEL":{"status":"UNSET","values":{}},'
     '"KURUMSAL":{"status":"UNSET","values":{}}}'::jsonb),
    ('R03', 'Çok sayıda nakit yatırma - Aynı hesaba eşik altı nakit yatırma',
     'Son 7 günde aynı hesaba gelen eşik altı nakit işlemlerini sayar.',
     FALSE, 1.000,
     '{"BIREYSEL":{"status":"UNSET","values":{}},'
     '"KURUMSAL":{"status":"UNSET","values":{}}}'::jsonb)
ON CONFLICT (rule_code) DO NOTHING;

UPDATE monitoring_rule
SET is_active = FALSE
WHERE rule_code IN ('R01', 'R02', 'R03');

INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
SELECT NULL, 'rule.migrated_weight', 'monitoring_rule', rule_code,
       jsonb_build_object(
           'old_weight', weight,
           'new_weight', CASE rule_code WHEN 'R02' THEN 0.450 ELSE 1.000 END
       )
FROM monitoring_rule
WHERE rule_code IN ('R01', 'R02', 'R03')
  AND weight <> CASE rule_code WHEN 'R02' THEN 0.450 ELSE 1.000 END;

UPDATE monitoring_rule
SET weight = CASE rule_code WHEN 'R02' THEN 0.450 ELSE 1.000 END
WHERE rule_code IN ('R01', 'R02', 'R03');
