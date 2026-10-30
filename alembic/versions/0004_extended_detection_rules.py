from alembic import op
import sqlalchemy as sa


revision = "0004_extended_detection_rules"
down_revision = "0003_rule_framework"
branch_labels = None
depends_on = None


UNSET_THRESHOLDS = (
    '{"BIREYSEL":{"status":"UNSET","values":{}},'
    '"KURUMSAL":{"status":"UNSET","values":{}}}'
)

RULES = (
    ("R04", "Gelir-hacim uyumsuzluğu", "Aylık gelir ile son dönemdeki müşteri transfer hacmini karşılaştırır."),
    ("R05", "Olağandışı tutar", "Bugünkü transferleri geçmiş log-tutar dağılımı ve gelir grubu ile karşılaştırır."),
    ("R06", "Hız artışı", "Bu haftaki transfer sayısını önceki haftalık dağılımdan beklenen sayıyla karşılaştırır."),
    ("R07", "Uyuyan hesap uyanması", "Hareketsiz hesaplarda yeniden başlayan yüksek hacimli hareketi arar."),
    ("R08", "Yeni hesapta yüksek hareket", "Yakın zamanda açılmış hesapların açılıştan bugüne transfer hacmini değerlendirir."),
    ("R09", "Nakit yoğunluğu", "Müşterinin güncel nakit payını önceki dönemle karşılaştırır."),
    ("R10", "Geçiş hesabı", "Gelen paranın çoğunu kısa sürede yeni alıcılara aktaran müşterileri arar."),
    ("R11", "Para toplama (fan-in)", "Kısa sürede yeni kaynaklardan gelen transferleri sayar."),
    ("R12", "Dağıtma (fan-out)", "Kısa sürede yeni alıcılara giden transferleri ve benzer tutarları değerlendirir."),
    ("R13", "Katmanlama zinciri", "Hızlı ve azalan tutarlı dış transfer zincirlerini arar."),
    ("R14", "Döngü ve ping-pong", "Dış transfer grafiğinde geri dönen yolları ve karşılıklı benzer tutarları arar."),
    ("R15", "Şüpheli hesapla temas", "Daha önce şüpheli olduğu onaylanan hesaplara doğrudan veya aracı üzerinden teması arar."),
)


def upgrade() -> None:
    bind = op.get_bind()
    for code, name, description in RULES:
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
            "DELETE FROM monitoring_rule "
            "WHERE rule_code BETWEEN 'R04' AND 'R15' "
            "AND NOT EXISTS ("
            "SELECT 1 FROM rule_result "
            "WHERE rule_result.rule_id = monitoring_rule.rule_id)"
        )
    )
