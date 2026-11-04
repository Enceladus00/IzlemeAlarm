from backend.detection.metadata import ParameterSpec, RuleDefinition, RuleStrategy
from backend.detection.parameters import R17Values


class MultipleAlertsRule(RuleStrategy):
    """Evaluated after the run's alerts are saved (stage 2).

    The work happens in SqlAlchemyDetectionRepository.persist_run, inside the same
    transaction: when a customer has open alerts from at least `min_rules` different
    rules within `window_days`, each open alert's severity is raised one step
    (low -> medium -> high), at most once per alert.
    """

    definition = RuleDefinition(
        code="R17",
        name="Çoklu uyarı",
        description="Aynı müşteride birden çok farklı kuraldan açık alarm varsa açık alarmların önemini bir kademe yükseltir.",
        steps=(
            "Müşterinin pencere içindeki açık alarmlarını, hariç tutulan kurallar dışında, kural bazında say (K).",
            "K en az kural sayısına ulaştıysa açık alarmların önemini bir kademe yükselt.",
            "Bir alarm R17 ile en fazla bir kez yükseltilir; her yükseltme denetim kaydına yazılır.",
        ),
        alert_mode="SEVERITY_RAISE",
        parameter_model=R17Values,
        parameters=(
            ParameterSpec("window_days", "integer", "days", "Alerts created within this many days are counted.", False),
            ParameterSpec("min_rules", "integer", "rules", "Distinct rules with open alerts needed to raise severity (K >= min_rules).", True),
            ParameterSpec("excluded_rules", "rule code list", "rule_code", "Rules not counted in K.", False),
            ParameterSpec("open_statuses", "status list", "alert status", "Alert statuses that count as open (new, in_review).", False),
        ),
        analyst_review_notes=(
            "The rule list's open statuses OPEN/IN_REVIEW map to the database values new/in_review.",
        ),
        feasibility="HIGH",
        feasibility_reason="Uses stored alerts and their statuses.",
        stage=2,
    )
