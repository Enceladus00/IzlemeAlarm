-- DEVELOPMENT: the administrator gets every permission again (undoes the K13
-- restriction from V5). Mirrors alembic/versions/0007_admin_all_permissions.py.
-- A permission added later must be granted to admin in that later script too.

INSERT INTO role_permission (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM app_role r CROSS JOIN permission p
WHERE r.role_code = 'admin'
ON CONFLICT DO NOTHING;

INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
VALUES (NULL, 'role.permissions_changed', 'role', 'migration:V6',
        '{"source":"V6","admin":"all permissions (development)"}'::jsonb);
