from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any

from backend.detection.metadata import (
    ParameterSpec,
    RawRuleResult,
    RuleDefinition,
    RuleResultEvidence,
    RuleStrategy,
)
from backend.detection.parameters import R18Values
from backend.models import Customer, Transaction


EXCLUDED_FROM_COMBINATION = frozenset({"R17", "R18"})
SCORE_QUANTUM = Decimal("0.0001")


def combined_score(contributions: list[Decimal], p: Decimal) -> Decimal:
    """A = min(1, (sum u_i^p)^(1/p)), rounded like every other score."""
    with localcontext() as context:
        context.prec = 28
        total = sum((u ** p for u in contributions if u > 0), Decimal("0"))
        if total <= 0:
            return Decimal("0.0000")
        value = total ** (Decimal("1") / p)
    # Capped at 1: alert.score is limited to [0, 1] in the database.
    return min(Decimal("1"), value).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


class CombinedScoreRule(RuleStrategy):
    definition = RuleDefinition(
        code="R18",
        name="Birleşik risk skoru",
        description="Aynı çalıştırmadaki tüm kural skorlarını ağırlıklarıyla p-normda birleştirir; eşiği aşarsa alarm açar.",
        steps=(
            "Aynı çalıştırmada bu müşteri için değerlendirilen kuralların skorlarını topla (R17 ve R18 hariç).",
            "Her kural için katkıyı hesapla: u = ağırlık × skor.",
            "A = (Σ u^p)^(1/p) değerini hesapla ve 1 ile sınırla.",
            "A alarm eşiğini geçerse alarm aç.",
        ),
        alert_mode="ALERT",
        parameter_model=R18Values,
        parameters=(
            ParameterSpec("p", "decimal", "norm", "p-norm exponent; 1 = weighted sum, larger p favours the strongest rule.", True),
            ParameterSpec("alert_threshold", "decimal", "score", "Combined score needed to open an alert.", True),
        ),
        analyst_review_notes=(
            "Runs after every other rule in the same detection run and uses the rule weights captured for that run.",
            "A is capped at 1 because alert scores are stored in [0, 1].",
        ),
        feasibility="HIGH",
        feasibility_reason="Uses the scores already computed in the same run.",
        stage=1,
    )

    def evaluate_combined(
        self,
        customers: list[Customer],
        parameter_sets: dict[str, dict[str, Any]],
        prior_results: list[RuleResultEvidence],
        weights: dict[str, Decimal],
        *,
        as_of: Any,
    ) -> list[RawRuleResult]:
        by_customer: dict[int, list[RuleResultEvidence]] = {}
        for result in prior_results:
            if (
                result.rule_code in EXCLUDED_FROM_COMBINATION
                or result.result_status != "evaluated"
                or result.score is None
            ):
                continue
            by_customer.setdefault(result.customer_id, []).append(result)
        output = []
        for customer in customers:
            values = parameter_sets[customer.customer_type]["values"]
            p = Decimal(str(values["p"]))
            contributions = []
            evidence: dict[int, Transaction] = {}
            for result in sorted(by_customer.get(customer.customer_id, []), key=lambda r: r.rule_code):
                weight = Decimal(str(weights.get(result.rule_code, Decimal("0"))))
                u = (weight * result.score).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)
                contributions.append(
                    {"rule_code": result.rule_code, "score": str(result.score), "weight": str(weight), "u": str(u)}
                )
                if u > 0:
                    for tx in result.transactions:
                        evidence[tx.transaction_id] = tx
            score = combined_score([Decimal(item["u"]) for item in contributions], p)
            top = sorted(
                (item for item in contributions if Decimal(item["u"]) > 0),
                key=lambda item: Decimal(item["u"]),
                reverse=True,
            )[:3]
            output.append(
                RawRuleResult(
                    customer_id=customer.customer_id,
                    customer_type=customer.customer_type,
                    raw_x=score,
                    transactions=list(evidence.values()),
                    step_trace=[
                        {"step": 1, "text": self.definition.steps[0], "status": "completed", "details": {
                            "evaluated_rule_count": len(contributions),
                        }},
                        {"step": 2, "text": self.definition.steps[1], "status": "completed", "details": {
                            "contributions": contributions,
                        }},
                        {"step": 3, "text": self.definition.steps[2], "status": "completed", "details": {
                            "p": str(p),
                            "A": str(score),
                            "top_rules": ", ".join(f"{item['rule_code']} ({item['u']})" for item in top),
                        }},
                        {"step": 4, "text": self.definition.steps[3], "status": "completed", "details": {
                            "alert_threshold": str(values["alert_threshold"]),
                            "score": str(score),
                        }},
                    ],
                    score_override=score,
                )
            )
        return output
