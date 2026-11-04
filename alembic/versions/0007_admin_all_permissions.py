"""DEVELOPMENT: the administrator gets every permission again.

0006 removed alert:view, alert:update and customer:view from admin (design K13).
During development the admin is a "god" user with access to everything; revert
this migration (alembic downgrade 0006_alert_workflow) to restore K13.
Mirrored in database/V6__admin_all_permissions.sql.

Note: this grants the permissions that exist now. A permission added by a later
migration must be granted to admin in that migration too.
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_admin_all_permissions"
down_revision = "0006_alert_workflow"
branch_labels = None
depends_on = None

K13_REMOVED = ("alert:view", "alert:update", "customer:view")
ADDED_IN_0006 = ("alert:escalate", "alert:confirm")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO role_permission (role_id, permission_id) "
            "SELECT r.role_id, p.permission_id FROM app_role r CROSS JOIN permission p "
            "WHERE r.role_code = 'admin' ON CONFLICT DO NOTHING"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details) "
            "VALUES (NULL, 'role.permissions_changed', 'role', 'migration:0007', "
            "CAST(:details AS jsonb))"
        ),
        {"details": '{"source":"alembic 0007","admin":"all permissions (development)"}'},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM role_permission WHERE "
            "role_id = (SELECT role_id FROM app_role WHERE role_code = 'admin') "
            "AND permission_id IN (SELECT permission_id FROM permission WHERE code = ANY(:codes))"
        ),
        {"codes": list(K13_REMOVED + ADDED_IN_0006)},
    )
