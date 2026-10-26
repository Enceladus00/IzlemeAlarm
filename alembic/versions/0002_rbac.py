from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "0002_rbac"
down_revision = "0001_existing_schema_baseline"
branch_labels = None
depends_on = None


PERMISSIONS = (
    ("user:manage", "Create, deactivate, and assign users"),
    ("role:manage", "Manage roles and their permissions"),
    ("upload:create", "Upload customer, account, and transaction CSV files"),
    ("upload:view", "View upload history and row error reports"),
    ("rule:view", "View monitoring rules and thresholds"),
    ("rule:edit", "Edit rules, thresholds, and run detection manually"),
    ("customer:view", "Search and view customers, accounts, and transactions"),
    ("alert:view", "View alerts and alert-scoped investigation data"),
    ("alert:update", "Change alert status and add investigation notes"),
    ("dashboard:view", "View dashboard and overview statistics"),
    ("audit:view", "View audit events"),
)


def upgrade() -> None:
    op.create_table(
        "app_role",
        sa.Column("role_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("role_code", sa.String(length=20), nullable=False, unique=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=text("true")),
    )
    op.create_table(
        "permission",
        sa.Column("permission_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "role_permission",
        sa.Column(
            "role_id",
            sa.BigInteger(),
            sa.ForeignKey("app_role.role_id"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            sa.BigInteger(),
            sa.ForeignKey("permission.permission_id"),
            primary_key=True,
        ),
    )

    bind = op.get_bind()
    bind.execute(
        text(
            "INSERT INTO app_role (role_code, name) VALUES "
            "('admin', 'Admin'), ('analyst', 'Analist') "
            "ON CONFLICT (role_code) DO NOTHING"
        )
    )
    has_auditors = bind.scalar(
        text("SELECT EXISTS (SELECT 1 FROM app_user WHERE role = 'auditor')")
    )
    if has_auditors:
        bind.execute(
            text(
                "INSERT INTO app_role (role_code, name) "
                "VALUES ('auditor', 'Auditor') ON CONFLICT (role_code) DO NOTHING"
            )
        )
    bind.execute(
        text(
            "INSERT INTO permission (code, description) VALUES "
            + ", ".join(
                f"('{code}', '{description.replace(chr(39), chr(39) * 2)}')"
                for code, description in PERMISSIONS
            )
            + " ON CONFLICT (code) DO NOTHING"
        )
    )

    op.add_column("app_user", sa.Column("role_id", sa.BigInteger(), nullable=True))
    bind.execute(
        text(
            "UPDATE app_user SET role_id = ("
            "SELECT role_id FROM app_role "
            "WHERE role_code = CASE app_user.role "
            "WHEN 'admin' THEN 'admin' "
            "WHEN 'auditor' THEN 'auditor' ELSE 'analyst' END)"
        )
    )
    for constraint in inspect(bind).get_check_constraints("app_user"):
        if "role" in (constraint.get("sqltext") or "").lower():
            op.drop_constraint(constraint["name"], "app_user", type_="check")
    op.alter_column("app_user", "role_id", nullable=False)
    op.create_foreign_key(
        "fk_app_user_role_id_app_role",
        "app_user",
        "app_role",
        ["role_id"],
        ["role_id"],
    )
    op.create_index("idx_app_user_role_id", "app_user", ["role_id"])
    op.drop_column("app_user", "role")

    bind.execute(
        text(
            "INSERT INTO role_permission (role_id, permission_id) "
            "SELECT r.role_id, p.permission_id FROM app_role r CROSS JOIN permission p "
            "WHERE r.role_code = 'admin' "
            "ON CONFLICT DO NOTHING"
        )
    )
    bind.execute(
        text(
            "INSERT INTO role_permission (role_id, permission_id) "
            "SELECT r.role_id, p.permission_id FROM app_role r "
            "JOIN permission p ON p.code IN "
            "('alert:view', 'alert:update', 'dashboard:view') "
            "WHERE r.role_code = 'analyst' "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.add_column("app_user", sa.Column("role", sa.String(length=20), nullable=True))
    bind.execute(
        text(
            "UPDATE app_user SET role = ("
            "SELECT CASE role_code WHEN 'admin' THEN 'admin' "
            "WHEN 'auditor' THEN 'auditor' ELSE 'analyst' END "
            "FROM app_role WHERE app_role.role_id = app_user.role_id)"
        )
    )
    op.alter_column("app_user", "role", nullable=False)
    op.create_check_constraint(
        "app_user_role_check",
        "app_user",
        "role IN ('admin', 'analyst', 'auditor')",
    )
    op.drop_index("idx_app_user_role_id", table_name="app_user")
    op.drop_constraint("fk_app_user_role_id_app_role", "app_user", type_="foreignkey")
    op.drop_column("app_user", "role_id")
    op.drop_table("role_permission")
    op.drop_table("permission")
    op.drop_table("app_role")
