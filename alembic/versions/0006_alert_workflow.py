"""Alert workflow roles (API design 7.1, K13) and rows for rules R16-R18, S1, S2.

Adds rows only; no table or column changes. Mirrored in
database/V5__alert_workflow.sql.
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_alert_workflow"
down_revision = "0005_system_overview_metrics"
branch_labels = None
depends_on = None


NEW_PERMISSIONS = (
    ("alert:escalate", "Escalate a new alert to a compliance officer"),
    ("alert:confirm", "Decide on escalated alerts and view any alert's customer context"),
)
ANALYST_ADDITIONS = ("alert:escalate", "rule:view")
# The spec also lists alert:update for compliance; it was left out on purpose so a
# compliance officer cannot close a new alert directly and skip the analyst step.
COMPLIANCE_PERMISSIONS = (
    "alert:view",
    "alert:confirm",
    "customer:view",
    "dashboard:view",
    "rule:view",
    "rule:edit",
    "audit:view",
)
# K13: administrators manage the system but do not see customer or alert content.
ADMIN_REMOVALS = ("alert:view", "alert:update", "customer:view")

UNSET_THRESHOLDS = (
    '{"BIREYSEL":{"status":"UNSET","values":{}},'
    '"KURUMSAL":{"status":"UNSET","values":{}}}'
)
NEW_RULES = (
    ("R16", "Listelenmiş ülke", "Listelenmiş (yüksek riskli) ülkelerle yapılan işlem hacmini değerlendirir."),
    ("S1", "Yuvarlak tutar", "Büyük ve yuvarlak tutarlı işlemlerin payını ölçer; yalnızca birleşik skora katkı verir."),
    ("S2", "Merkez hesap", "Müşterinin karşı taraf sayısını benzer müşterilerle karşılaştırır; yalnızca birleşik skora katkı verir."),
    ("R17", "Çoklu uyarı", "Aynı müşteride birden çok farklı kuraldan açık alarm varsa alarmların önemini yükseltir."),
    ("R18", "Birleşik risk skoru", "Aynı çalıştırmadaki kural skorlarını ağırlıklarıyla birleştirir."),
)


def _grant(bind, role_code: str, codes: tuple[str, ...]) -> None:
    bind.execute(
        sa.text(
            "INSERT INTO role_permission (role_id, permission_id) "
            "SELECT r.role_id, p.permission_id FROM app_role r "
            "JOIN permission p ON p.code = ANY(:codes) "
            "WHERE r.role_code = :role ON CONFLICT DO NOTHING"
        ),
        {"codes": list(codes), "role": role_code},
    )


def _revoke(bind, role_code: str, codes: tuple[str, ...]) -> None:
    bind.execute(
        sa.text(
            "DELETE FROM role_permission WHERE "
            "role_id = (SELECT role_id FROM app_role WHERE role_code = :role) "
            "AND permission_id IN (SELECT permission_id FROM permission WHERE code = ANY(:codes))"
        ),
        {"codes": list(codes), "role": role_code},
    )


def upgrade() -> None:
    bind = op.get_bind()
    for code, description in NEW_PERMISSIONS:
        bind.execute(
            sa.text(
                "INSERT INTO permission (code, description) VALUES (:code, :description) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "description": description},
        )
    bind.execute(
        sa.text(
            "INSERT INTO app_role (role_code, name) VALUES ('compliance', 'Uyum Görevlisi') "
            "ON CONFLICT (role_code) DO NOTHING"
        )
    )
    _grant(bind, "analyst", ANALYST_ADDITIONS)
    _grant(bind, "compliance", COMPLIANCE_PERMISSIONS)
    _revoke(bind, "admin", ADMIN_REMOVALS)
    bind.execute(
        sa.text(
            "INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details) "
            "VALUES (NULL, 'role.permissions_changed', 'role', 'migration:0006', "
            "CAST(:details AS jsonb))"
        ),
        {
            "details": (
                '{"source":"alembic 0006",'
                '"analyst_added":["alert:escalate","rule:view"],'
                '"compliance_created":["alert:view","alert:confirm","customer:view",'
                '"dashboard:view","rule:view","rule:edit","audit:view"],'
                '"admin_removed":["alert:view","alert:update","customer:view"]}'
            )
        },
    )
    for code, name, description in NEW_RULES:
        bind.execute(
            sa.text(
                "INSERT INTO monitoring_rule "
                "(rule_code, name, description, is_active, weight, thresholds) "
                "VALUES (:code, :name, :description, false, 1.000, "
                "CAST(:thresholds AS jsonb)) ON CONFLICT (rule_code) DO NOTHING"
            ),
            {
                "code": code,
                "name": name,
                "description": description,
                "thresholds": UNSET_THRESHOLDS,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM monitoring_rule WHERE rule_code IN ('R16','S1','S2','R17','R18') "
            "AND NOT EXISTS (SELECT 1 FROM rule_result WHERE rule_result.rule_id = monitoring_rule.rule_id) "
            "AND NOT EXISTS (SELECT 1 FROM alert WHERE alert.rule_id = monitoring_rule.rule_id)"
        )
    )
    _grant(bind, "admin", ADMIN_REMOVALS)
    _revoke(bind, "analyst", ANALYST_ADDITIONS)
    bind.execute(
        sa.text(
            "DELETE FROM role_permission WHERE role_id = "
            "(SELECT role_id FROM app_role WHERE role_code = 'compliance')"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM app_role WHERE role_code = 'compliance' "
            "AND NOT EXISTS (SELECT 1 FROM app_user WHERE app_user.role_id = app_role.role_id)"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM permission WHERE code IN ('alert:escalate', 'alert:confirm') "
            "AND NOT EXISTS (SELECT 1 FROM role_permission rp "
            "WHERE rp.permission_id = permission.permission_id)"
        )
    )
