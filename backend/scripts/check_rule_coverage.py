"""Read-only: which rules would alert on the MUS-* example data?

Runs the detection engine in memory with the database's current rule
parameters, treating every rule as active, and prints per rule the best score
and how many customers would get an alert. Nothing is written.

Run:  python -m backend.scripts.check_rule_coverage [--prefix MUS-]
"""

import argparse
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from backend.database import create_independent_session
from backend.detection.engine import DetectionEngine
from backend.detection.metadata import DetectionContext
from backend.models import Customer
from backend.repositories.detection_repository import ALERT_THRESHOLD, SqlAlchemyDetectionRepository


def check(prefix: str) -> None:
    with create_independent_session() as session:
        repository = SqlAlchemyDetectionRepository(session)
        ids = set(session.scalars(select(Customer.customer_id).where(Customer.customer_no.like(f"{prefix}%"))))
        rules = repository.list_rules()
        for rule in rules:
            # in memory only; the session is rolled back. Legacy R1-R4 rows have no implementation.
            rule.is_active = rule.rule_code not in {"R1", "R2", "R3", "R4"}
        suspicious = repository.list_customers_with_history_status("confirmed_suspicious") & ids
        context = DetectionContext(
            suspicious_customer_ids_by_status={"confirmed_suspicious": suspicious},
            suspicious_account_ids_by_status={
                "confirmed_suspicious": repository.list_account_ids_for_customers(suspicious)
            },
        )
        evaluation = DetectionEngine().evaluate(
            repository.list_active_customers(ids),
            repository.list_active_transactions(ids),
            {rule.rule_code: rule for rule in rules},
            as_of=datetime.now(),
            context=context,
        )
        session.rollback()

    best: dict[str, Decimal] = defaultdict(lambda: Decimal(-1))
    alerts: dict[str, int] = defaultdict(int)
    modes: dict[str, str] = {}
    for result in evaluation.results:
        if result.result_status != "evaluated" or result.score is None:
            continue
        best[result.rule_code] = max(best[result.rule_code], result.score)
        modes[result.rule_code] = result.alert_mode
        if result.score >= (result.alert_threshold or ALERT_THRESHOLD):
            alerts[result.rule_code] += 1
    codes = sorted({r.rule_code for r in evaluation.results})
    for code in codes:
        score = best.get(code)
        print(f"{code:4} mode={modes.get(code, '-'):7} best={score if score is not None and score >= 0 else '-'} hits={alerts.get(code, 0)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="MUS-")
    check(parser.parse_args().prefix)
