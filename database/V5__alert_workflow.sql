-- Alert workflow roles (API design 7.1, K13) and rows for rules R16-R18, S1, S2.
-- Rows only; no table or column changes. Mirrors alembic/versions/0006_alert_workflow.py.

INSERT INTO permission (code, description) VALUES
    ('alert:escalate', 'Escalate a new alert to a compliance officer'),
    ('alert:confirm', 'Decide on escalated alerts and view any alert''s customer context')
ON CONFLICT (code) DO NOTHING;

INSERT INTO app_role (role_code, name) VALUES ('compliance', 'Uyum Görevlisi')
ON CONFLICT (role_code) DO NOTHING;

-- Analyst: may escalate and read rule definitions.
INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM app_role r
JOIN permission p ON p.code IN ('alert:escalate', 'rule:view')
WHERE r.role_code = 'analyst'
ON CONFLICT DO NOTHING;

-- Compliance officer. alert:update is intentionally NOT granted: a compliance
-- officer must not close a new alert directly and skip the analyst step.
INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id FROM app_role r
JOIN permission p ON p.code IN (
    'alert:view', 'alert:confirm', 'customer:view', 'dashboard:view',
    'rule:view', 'rule:edit', 'audit:view'
)
WHERE r.role_code = 'compliance'
ON CONFLICT DO NOTHING;

-- K13: administrators do not see customer or alert content.
DELETE FROM role_permission
WHERE role_id = (SELECT role_id FROM app_role WHERE role_code = 'admin')
  AND permission_id IN (
      SELECT permission_id FROM permission
      WHERE code IN ('alert:view', 'alert:update', 'customer:view')
  );

INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
VALUES (
    NULL, 'role.permissions_changed', 'role', 'migration:V5',
    '{"source":"V5","analyst_added":["alert:escalate","rule:view"],"compliance_created":["alert:view","alert:confirm","customer:view","dashboard:view","rule:view","rule:edit","audit:view"],"admin_removed":["alert:view","alert:update","customer:view"]}'::jsonb
);

-- New rules start inactive with no parameters (UNSET for both customer types).
INSERT INTO monitoring_rule (rule_code, name, description, is_active, weight, thresholds) VALUES
    ('R16', 'Listelenmiş ülke', 'Listelenmiş (yüksek riskli) ülkelerle yapılan işlem hacmini değerlendirir.', false, 1.000,
     '{"BIREYSEL":{"status":"UNSET","values":{}},"KURUMSAL":{"status":"UNSET","values":{}}}'::jsonb),
    ('S1', 'Yuvarlak tutar', 'Büyük ve yuvarlak tutarlı işlemlerin payını ölçer; yalnızca birleşik skora katkı verir.', false, 1.000,
     '{"BIREYSEL":{"status":"UNSET","values":{}},"KURUMSAL":{"status":"UNSET","values":{}}}'::jsonb),
    ('S2', 'Merkez hesap', 'Müşterinin karşı taraf sayısını benzer müşterilerle karşılaştırır; yalnızca birleşik skora katkı verir.', false, 1.000,
     '{"BIREYSEL":{"status":"UNSET","values":{}},"KURUMSAL":{"status":"UNSET","values":{}}}'::jsonb),
    ('R17', 'Çoklu uyarı', 'Aynı müşteride birden çok farklı kuraldan açık alarm varsa alarmların önemini yükseltir.', false, 1.000,
     '{"BIREYSEL":{"status":"UNSET","values":{}},"KURUMSAL":{"status":"UNSET","values":{}}}'::jsonb),
    ('R18', 'Birleşik risk skoru', 'Aynı çalıştırmadaki kural skorlarını ağırlıklarıyla birleştirir.', false, 1.000,
     '{"BIREYSEL":{"status":"UNSET","values":{}},"KURUMSAL":{"status":"UNSET","values":{}}}'::jsonb)
ON CONFLICT (rule_code) DO NOTHING;
