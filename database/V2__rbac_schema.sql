CREATE TABLE app_role (
    role_id BIGSERIAL PRIMARY KEY,
    role_code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE permission (
    permission_id BIGSERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE role_permission (
    role_id BIGINT NOT NULL REFERENCES app_role(role_id),
    permission_id BIGINT NOT NULL REFERENCES permission(permission_id),
    PRIMARY KEY (role_id, permission_id)
);

INSERT INTO app_role (role_code, name) VALUES
    ('admin', 'Admin'),
    ('analyst', 'Analist')
ON CONFLICT (role_code) DO NOTHING;

INSERT INTO app_role (role_code, name)
SELECT 'auditor', 'Auditor'
WHERE EXISTS (SELECT 1 FROM app_user WHERE role = 'auditor')
ON CONFLICT (role_code) DO NOTHING;

INSERT INTO permission (code, description) VALUES
    ('user:manage', 'Create, deactivate, and assign users'),
    ('role:manage', 'Manage roles and their permissions'),
    ('upload:create', 'Upload customer, account, and transaction CSV files'),
    ('upload:view', 'View upload history and row error reports'),
    ('rule:view', 'View monitoring rules and thresholds'),
    ('rule:edit', 'Edit rules, thresholds, and run detection manually'),
    ('customer:view', 'Search and view customers, accounts, and transactions'),
    ('alert:view', 'View alerts and alert-scoped investigation data'),
    ('alert:update', 'Change alert status and add investigation notes'),
    ('dashboard:view', 'View dashboard and overview statistics'),
    ('audit:view', 'View audit events')
ON CONFLICT (code) DO NOTHING;

ALTER TABLE app_user ADD COLUMN role_id BIGINT REFERENCES app_role(role_id);
UPDATE app_user SET role_id = (
    SELECT role_id FROM app_role
    WHERE role_code = CASE app_user.role
        WHEN 'admin' THEN 'admin'
        WHEN 'auditor' THEN 'auditor'
        ELSE 'analyst'
    END
);

DO $$
DECLARE constraint_row RECORD;
BEGIN
    FOR constraint_row IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'app_user'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%role%'
    LOOP
        EXECUTE format(
            'ALTER TABLE app_user DROP CONSTRAINT %I',
            constraint_row.conname
        );
    END LOOP;
END;
$$;

ALTER TABLE app_user ALTER COLUMN role_id SET NOT NULL;
ALTER TABLE app_user DROP COLUMN role;
CREATE INDEX idx_app_user_role_id ON app_user(role_id);

INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM app_role r CROSS JOIN permission p
WHERE r.role_code = 'admin'
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM app_role r
JOIN permission p ON p.code IN ('alert:view', 'alert:update', 'dashboard:view')
WHERE r.role_code = 'analyst'
ON CONFLICT DO NOTHING;
