from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_rule_framework"
down_revision = "0002_rbac"
branch_labels = None
depends_on = None


UNSET_THRESHOLDS = (
    '{"BIREYSEL":{"status":"UNSET","values":{}},'
    '"KURUMSAL":{"status":"UNSET","values":{}}}'
)


def upgrade() -> None:
    op.add_column(
        "monitoring_rule",
        sa.Column("weight", sa.Numeric(4, 3), nullable=False, server_default="1.000"),
    )
    op.create_check_constraint(
        "ck_monitoring_rule_weight_range",
        "monitoring_rule",
        "weight >= 0 AND weight <= 1",
    )
    op.add_column("alert", sa.Column("score", sa.Numeric(5, 4), nullable=True))
    op.create_check_constraint(
        "ck_alert_score_range",
        "alert",
        "score IS NULL OR (score >= 0 AND score <= 1)",
    )

    op.create_table(
        "detection_run",
        sa.Column("run_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_detection_run_status",
        ),
    )
    op.create_table(
        "rule_result",
        sa.Column("result_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("detection_run.run_id"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            sa.BigInteger(),
            sa.ForeignKey("monitoring_rule.rule_id"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.BigInteger(),
            sa.ForeignKey("customer.customer_id"),
            nullable=False,
        ),
        sa.Column("customer_type", sa.String(length=10), nullable=True),
        sa.Column("weight_snapshot", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "parameter_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("parameter_status", sa.String(length=20), nullable=False),
        sa.Column("result_status", sa.String(length=30), nullable=False),
        sa.Column("raw_x", sa.Numeric(18, 6), nullable=True),
        sa.Column("score", sa.Numeric(5, 4), nullable=True),
        sa.Column("alert_mode", sa.String(length=20), nullable=False),
        sa.Column(
            "step_trace",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "run_id",
            "rule_id",
            "customer_id",
            name="uq_rule_result_run_rule_customer",
        ),
        sa.CheckConstraint(
            "parameter_status IN ('UNSET', 'PROVISIONAL', 'APPROVED')",
            name="ck_rule_result_parameter_status",
        ),
        sa.CheckConstraint(
            "result_status IN ('evaluated', 'skipped_unset', 'skipped_customer_type')",
            name="ck_rule_result_result_status",
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)",
            name="ck_rule_result_score_range",
        ),
        sa.CheckConstraint(
            "weight_snapshot >= 0 AND weight_snapshot <= 1",
            name="ck_rule_result_weight_range",
        ),
    )
    op.create_table(
        "rule_result_transaction",
        sa.Column(
            "result_id",
            sa.BigInteger(),
            sa.ForeignKey("rule_result.result_id"),
            primary_key=True,
        ),
        sa.Column(
            "transaction_id",
            sa.BigInteger(),
            sa.ForeignKey("transaction.transaction_id"),
            primary_key=True,
        ),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO audit_log "
            "(actor_id, action, entity_type, entity_id, details) "
            "SELECT NULL, 'rule.migrated_inactive', 'monitoring_rule', rule_code, "
            "jsonb_build_object('old_is_active', is_active, 'new_is_active', false) "
            "FROM monitoring_rule "
            "WHERE rule_code IN ('R1', 'R2', 'R3', 'R4') AND is_active = true"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE monitoring_rule SET is_active = false "
            "WHERE rule_code IN ('R1', 'R2', 'R3', 'R4')"
        )
    )
    for code, name, description, weight in (
        (
            "R01",
            "Bölme - Limitin hemen altında birden çok işlem",
            "Son 7 günde limitin hemen altındaki işlemleri, üst limit ve gelire göre değerlendirir.",
            1.000,
        ),
        (
            "R02",
            "Büyük tek işlem - Limiti aşan işlem (büyüklük sinyali)",
            "Müşteri tipi ve para birimi limitini aşan işlemi INFO sinyali olarak kaydeder.",
            0.450,
        ),
        (
            "R03",
            "Çok sayıda nakit yatırma - Aynı hesaba eşik altı nakit yatırma",
            "Son 7 günde aynı hesaba gelen eşik altı nakit işlemlerini sayar.",
            1.000,
        ),
    ):
        bind.execute(
            sa.text(
                "INSERT INTO monitoring_rule "
                "(rule_code, name, description, is_active, weight, thresholds) "
                "VALUES (:code, :name, :description, false, :weight, "
                "CAST(:thresholds AS jsonb)) ON CONFLICT (rule_code) DO NOTHING"
            ),
            {
                "code": code,
                "name": name,
                "description": description,
                "weight": weight,
                "thresholds": UNSET_THRESHOLDS,
            },
        )
    bind.execute(
        sa.text(
            "UPDATE monitoring_rule SET is_active = false "
            "WHERE rule_code IN ('R01', 'R02', 'R03')"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO audit_log "
            "(actor_id, action, entity_type, entity_id, details) "
            "SELECT NULL, 'rule.migrated_weight', 'monitoring_rule', rule_code, "
            "jsonb_build_object('old_weight', weight, 'new_weight', "
            "CASE rule_code WHEN 'R02' THEN 0.450 ELSE 1.000 END) "
            "FROM monitoring_rule "
            "WHERE rule_code IN ('R01', 'R02', 'R03') "
            "AND weight <> CASE rule_code WHEN 'R02' THEN 0.450 ELSE 1.000 END"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE monitoring_rule SET weight = "
            "CASE rule_code WHEN 'R02' THEN 0.450 ELSE 1.000 END "
            "WHERE rule_code IN ('R01', 'R02', 'R03')"
        )
    )


def downgrade() -> None:
    op.drop_table("rule_result_transaction")
    op.drop_table("rule_result")
    op.drop_table("detection_run")
    op.drop_constraint("ck_alert_score_range", "alert", type_="check")
    op.drop_column("alert", "score")
    op.drop_constraint(
        "ck_monitoring_rule_weight_range", "monitoring_rule", type_="check"
    )
    op.drop_column("monitoring_rule", "weight")
    op.execute(
        "UPDATE monitoring_rule AS rule SET is_active = "
        "(log.details->>'old_is_active')::boolean "
        "FROM audit_log AS log "
        "WHERE log.action = 'rule.migrated_inactive' "
        "AND log.entity_type = 'monitoring_rule' "
        "AND log.entity_id = rule.rule_code "
        "AND rule.rule_code IN ('R1', 'R2', 'R3', 'R4')"
    )
