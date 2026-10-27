import logging
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from backend.detection.engine import DetectionEngine
from backend.detection.evidence import deduplication_key
from backend.detection.evaluation import DetectionEvaluation
from backend.detection.metadata import RuleResultEvidence
from backend.detection.parameters import validate_rule_parameters
from backend.detection.registry import load_rule_registry
from backend.detection.rules.r01_splitting import SplittingRule
from backend.detection.rules.r02_large_single import LargeSingleTransactionRule
from backend.detection.rules.r03_cash_deposits import CashDepositsRule
from backend.detection.scoring import calculate_score
from backend.demo import DEMO_RULE_OVERRIDES
from backend.models import Alert, RuleResult
from backend.repositories.detection_repository import SqlAlchemyDetectionRepository


AS_OF = datetime(2026, 1, 8)


def make_customer(
    customer_id: int,
    customer_type: str = "BIREYSEL",
    income: str | None = "1000",
) -> SimpleNamespace:
    return SimpleNamespace(
        customer_id=customer_id,
        customer_type=customer_type,
        monthly_income=Decimal(income) if income is not None else None,
    )


def make_transaction(
    transaction_id: int,
    amount: str,
    *,
    sender_id: int = 1,
    receiver_id: int = 2,
    sender_account_id: int = 11,
    receiver_account_id: int = 22,
    currency: str = "TRY",
    channel: str = "atm",
    tx_time: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        amount=Decimal(amount),
        currency=currency,
        channel=channel,
        tx_time=tx_time or AS_OF - timedelta(days=1),
        sender_account_id=sender_account_id,
        receiver_account_id=receiver_account_id,
        sender_account=SimpleNamespace(customer_id=sender_id),
        receiver_account=SimpleNamespace(customer_id=receiver_id),
    )


def parameter_set(values: dict[str, object], status: str = "PROVISIONAL"):
    return {"status": status, "values": values}


def r01_values(**overrides: object) -> dict[str, object]:
    return {
        "limits": {"TRY": "100"},
        "x_esik": "1",
        "x_kesin": "3",
        "minimum_income_ratio": "0.001",
        "income_currency": "TRY",
        **overrides,
    }


def r03_values(**overrides: object) -> dict[str, object]:
    return {
        "limits": {"TRY": "100"},
        "x_esik": "1",
        "x_kesin": "3",
        "cash_channels": ["atm", "branch"],
        **overrides,
    }


def rule_rows(active_code: str | None = None, thresholds=None):
    rows = {
        code: SimpleNamespace(
            rule_code=code,
            is_active=code == active_code,
            thresholds=thresholds if code == active_code else {},
        )
        for code in ("R01", "R02", "R03")
    }
    return rows


class DetectionStrategyTests(unittest.TestCase):
    def test_sigmoid_has_required_anchor_values(self) -> None:
        self.assertEqual(
            calculate_score(Decimal("4"), x_esik=Decimal("4"), x_kesin=Decimal("10")),
            Decimal("0.5000"),
        )
        self.assertEqual(
            calculate_score(Decimal("10"), x_esik=Decimal("4"), x_kesin=Decimal("10")),
            Decimal("0.9000"),
        )

    def test_r01_includes_lower_band_boundary_and_excludes_exact_limit(self) -> None:
        rule = SplittingRule()
        customer = make_customer(1)
        lower = make_transaction(1, "90", sender_id=1)
        at_limit = make_transaction(2, "100", sender_id=1)
        lower_result = rule.evaluate_raw(
            [customer],
            [lower],
            {"BIREYSEL": parameter_set(r01_values())},
            as_of=AS_OF,
        )[0]
        limit_result = rule.evaluate_raw(
            [customer],
            [at_limit],
            {"BIREYSEL": parameter_set(r01_values())},
            as_of=AS_OF,
        )[0]

        self.assertEqual(lower_result.raw_x, Decimal("1"))
        self.assertEqual(lower_result.transactions, [lower])
        self.assertFalse(lower_result.force_zero)
        self.assertEqual(limit_result.raw_x, Decimal("0"))
        self.assertFalse(limit_result.step_trace[2]["details"]["limit_exceeded"])
        self.assertEqual(limit_result.transactions, [])

    def test_r01_transaction_above_limit_forces_zero(self) -> None:
        result = SplittingRule().evaluate_raw(
            [make_customer(1)],
            [
                make_transaction(1, "95", sender_id=1),
                make_transaction(2, "100.01", sender_id=1),
            ],
            {"BIREYSEL": parameter_set(r01_values())},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("1"))
        self.assertTrue(result.force_zero)
        self.assertEqual(
            calculate_score(
                result.raw_x,
                x_esik=result.x_esik,
                x_kesin=result.x_kesin,
                force_zero=result.force_zero,
            ),
            Decimal("0.0000"),
        )

    def test_r02_amount_equal_to_limit_scores_one(self) -> None:
        values = {"limits": {"TRY": "100"}}
        result = LargeSingleTransactionRule().evaluate_raw(
            [make_customer(1)],
            [make_transaction(1, "100", sender_id=1)],
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(
            calculate_score(result.raw_x, binary_limit=result.binary_limit),
            Decimal("1.0000"),
        )
        self.assertEqual(result.transactions[0].transaction_id, 1)

    def test_r03_amount_equal_to_limit_is_not_counted(self) -> None:
        result = CashDepositsRule().evaluate_raw(
            [make_customer(2)],
            [
                make_transaction(
                    1,
                    "100",
                    receiver_id=2,
                    receiver_account_id=22,
                    channel="atm",
                )
            ],
            {"BIREYSEL": parameter_set(r03_values())},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("0"))
        self.assertEqual(result.transactions, [])
        self.assertLess(
            calculate_score(
                result.raw_x,
                x_esik=result.x_esik,
                x_kesin=result.x_kesin,
            ),
            Decimal("0.5"),
        )

    def test_r03_counts_only_incoming_cash_channels_on_same_account(self) -> None:
        transactions = [
            make_transaction(1, "50", sender_id=1, receiver_id=2, receiver_account_id=22),
            make_transaction(2, "50", sender_id=3, receiver_id=2, receiver_account_id=22),
            make_transaction(
                3,
                "50",
                sender_id=1,
                receiver_id=2,
                receiver_account_id=22,
                channel="mobile",
            ),
        ]
        result = CashDepositsRule().evaluate_raw(
            [make_customer(2)],
            transactions,
            {"BIREYSEL": parameter_set(r03_values())},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("2"))
        self.assertEqual([tx.transaction_id for tx in result.transactions], [1, 2])

    def test_parameters_are_selected_by_customer_type_and_trace_is_persistable(self) -> None:
        thresholds = {
            "BIREYSEL": parameter_set({"limits": {"TRY": "50"}}),
            "KURUMSAL": parameter_set({"limits": {"TRY": "100"}}),
        }
        customers = [make_customer(1, "BIREYSEL"), make_customer(2, "KURUMSAL")]
        transaction = make_transaction(1, "75", sender_id=1, receiver_id=2)
        evaluation = DetectionEngine().evaluate(
            customers,
            [transaction],
            rule_rows("R02", thresholds),
            as_of=AS_OF,
        )
        results = {result.customer_id: result for result in evaluation.results}

        self.assertEqual(results[1].score, Decimal("1.0000"))
        self.assertEqual(results[2].score, Decimal("0.0000"))
        self.assertEqual(
            results[1].parameter_snapshot["values"]["limits"]["TRY"], "50"
        )
        self.assertEqual(
            [step["step"] for step in results[1].step_trace], [1, 2, 3]
        )
        self.assertEqual(results[1].parameter_status, "PROVISIONAL")

    def test_demo_parameter_override_runs_inactive_rule_without_mutating_row(self) -> None:
        rows = rule_rows()
        customer = make_customer(1)
        transaction = make_transaction(1, "100", sender_id=1)
        thresholds = {
            "BIREYSEL": parameter_set({"limits": {"TRY": "100"}}),
            "KURUMSAL": {"status": "UNSET", "values": {}},
        }
        evaluation = DetectionEngine().evaluate(
            [customer],
            [transaction],
            rows,
            as_of=AS_OF,
            rule_overrides={"R02": thresholds},
        )

        self.assertEqual(evaluation.results[0].score, Decimal("1.0000"))
        self.assertTrue(evaluation.summary["demo_only"])
        self.assertFalse(rows["R02"].is_active)
        self.assertEqual(rows["R02"].thresholds, {})

    def test_demo_synthetic_scenarios_trigger_r01_r02_and_r03(self) -> None:
        customers = [
            make_customer(1, income="50000"),
            make_customer(2, income="50000"),
            make_customer(3, income="50000"),
        ]
        transactions = [
            make_transaction(101, "9500", sender_id=1, receiver_id=4),
            make_transaction(102, "9800", sender_id=1, receiver_id=5),
            make_transaction(103, "16000", sender_id=2, receiver_id=1),
            make_transaction(
                104,
                "500",
                sender_id=4,
                receiver_id=3,
                receiver_account_id=33,
                channel="atm",
            ),
            make_transaction(
                105,
                "600",
                sender_id=5,
                receiver_id=3,
                receiver_account_id=33,
                channel="branch",
            ),
            make_transaction(
                106,
                "700",
                sender_id=6,
                receiver_id=3,
                receiver_account_id=33,
                channel="atm",
            ),
        ]
        evaluation = DetectionEngine().evaluate(
            customers,
            transactions,
            rule_rows(),
            as_of=AS_OF,
            rule_overrides=DEMO_RULE_OVERRIDES,
        )
        results = {
            (result.rule_code, result.customer_id): result
            for result in evaluation.results
        }

        self.assertEqual(results[("R01", 1)].score, Decimal("0.7500"))
        self.assertEqual(results[("R01", 1)].parameter_status, "PROVISIONAL")
        self.assertEqual(results[("R02", 2)].score, Decimal("1.0000"))
        self.assertEqual(results[("R02", 2)].alert_mode, "SIGNAL_ONLY")
        self.assertEqual(results[("R03", 3)].score, Decimal("0.9000"))
        self.assertEqual([tx.transaction_id for tx in results[("R03", 3)].transactions], [104, 105, 106])

    def test_unset_parameters_skip_and_provisional_parameters_warn(self) -> None:
        customers = [make_customer(1)]
        unset = {
            "BIREYSEL": {"status": "UNSET", "values": {}},
            "KURUMSAL": {"status": "UNSET", "values": {}},
        }
        with self.assertLogs("backend.detection.engine", level=logging.WARNING) as logs:
            skipped = DetectionEngine().evaluate(
                customers, [], rule_rows("R02", unset), as_of=AS_OF
            )
        self.assertEqual(skipped.results[0].result_status, "skipped_unset")
        self.assertIn("status=UNSET", logs.output[0])

        provisional = {
            "BIREYSEL": parameter_set({"limits": {"TRY": "100"}}),
            "KURUMSAL": {"status": "UNSET", "values": {}},
        }
        with self.assertLogs("backend.detection.engine", level=logging.WARNING) as logs:
            evaluated = DetectionEngine().evaluate(
                customers, [], rule_rows("R02", provisional), as_of=AS_OF
            )
        self.assertEqual(evaluated.results[0].parameter_status, "PROVISIONAL")
        self.assertIn("PROVISIONAL", logs.output[0])

    def test_threshold_validation_rejects_missing_or_ordered_values(self) -> None:
        invalid = {
            "BIREYSEL": parameter_set(r01_values(x_esik="3", x_kesin="3"), "APPROVED"),
            "KURUMSAL": {"status": "UNSET", "values": {}},
        }
        with self.assertRaises(ValueError):
            validate_rule_parameters("R01", SplittingRule.definition.parameter_model, invalid)

        incomplete = {"BIREYSEL": {"status": "UNSET", "values": {}}}
        with self.assertRaises(ValueError):
            validate_rule_parameters("R01", SplittingRule.definition.parameter_model, incomplete)

    def test_registry_rejects_missing_rule_rows_and_active_implementations(self) -> None:
        registry = load_rule_registry()
        self.assertEqual(set(registry), {"R01", "R02", "R03"})
        missing_rule_row = rule_rows()
        del missing_rule_row["R03"]
        with self.assertRaisesRegex(RuntimeError, "implementations_without_database_row"):
            DetectionEngine().evaluate([], [], missing_rule_row, as_of=AS_OF)
        unknown = rule_rows()
        unknown["R04"] = SimpleNamespace(
            rule_code="R04", is_active=True, thresholds={}
        )
        with self.assertRaisesRegex(RuntimeError, "active_rules_without_implementation"):
            DetectionEngine().evaluate([], [], unknown, as_of=AS_OF)

    def test_as_of_excludes_transactions_at_or_after_the_injected_time(self) -> None:
        transaction = make_transaction(
            1, "100", sender_id=1, tx_time=AS_OF
        )
        evaluation = DetectionEngine().evaluate(
            [make_customer(1)],
            [transaction],
            rule_rows(
                "R02",
                {
                    "BIREYSEL": parameter_set({"limits": {"TRY": "100"}}),
                    "KURUMSAL": {"status": "UNSET", "values": {}},
                },
            ),
            as_of=AS_OF,
        )
        self.assertEqual(evaluation.results[0].score, Decimal("0.0000"))
        self.assertEqual(evaluation.results[0].transactions, [])

    def test_unknown_customer_type_and_unlisted_currency_are_counted(self) -> None:
        thresholds = {
            "BIREYSEL": parameter_set({"limits": {"TRY": "100"}}),
            "KURUMSAL": {"status": "UNSET", "values": {}},
        }
        unknown_type = make_customer(1, "OTHER")
        unknown_result = DetectionEngine().evaluate(
            [unknown_type],
            [],
            rule_rows("R02", thresholds),
            as_of=AS_OF,
        )
        self.assertEqual(
            unknown_result.results[0].result_status, "skipped_customer_type"
        )
        self.assertEqual(unknown_result.summary["unknown_customer_type_count"], 1)

        unlisted = make_transaction(
            1, "500", sender_id=1, currency="USD"
        )
        ignored_result = DetectionEngine().evaluate(
            [make_customer(1)],
            [unlisted],
            rule_rows("R02", thresholds),
            as_of=AS_OF,
        )
        self.assertEqual(
            ignored_result.summary["rules"]["R02"][
                "ignored_currency_transaction_count"
            ],
            1,
        )

    def test_deduplication_is_stable_and_customer_scoped(self) -> None:
        transactions = [make_transaction(7, "10"), make_transaction(3, "10")]
        key = deduplication_key("R01", transactions, customer_id=42)
        self.assertEqual(
            key,
            deduplication_key("R01", transactions[::-1], customer_id=42),
        )
        self.assertNotEqual(
            key, deduplication_key("R01", transactions, customer_id=43)
        )

    def test_persisting_the_same_alert_twice_is_idempotent(self) -> None:
        class FakeResult:
            def __init__(self, rows=()):
                self._rows = list(rows)

            def all(self):
                return self._rows

        class UniqueAlertSession:
            def __init__(self):
                self.pending = []
                self.alert_keys = {}
                self.next_result_id = 1
                self.next_alert_id = 1

            def add(self, value):
                self.pending.append(value)

            def add_all(self, values):
                self.pending.extend(values)

            def flush(self):
                for value in self.pending:
                    if isinstance(value, RuleResult) and value.result_id is None:
                        value.result_id = self.next_result_id
                        self.next_result_id += 1

            def execute(self, statement):
                if statement.table.name != Alert.__tablename__:
                    return FakeResult()
                inserted = []
                for row in statement._multi_values[0]:
                    key = row[Alert.__table__.c.deduplication_key]
                    if key not in self.alert_keys:
                        alert_id = self.next_alert_id
                        self.next_alert_id += 1
                        self.alert_keys[key] = alert_id
                        inserted.append((alert_id, key))
                return FakeResult(inserted)

            def commit(self):
                self.pending.clear()

            def rollback(self):
                self.pending.clear()

        transaction = make_transaction(91, "100", sender_id=1)
        result = RuleResultEvidence(
            rule_code="R01",
            customer_id=1,
            customer_type="BIREYSEL",
            parameter_snapshot={"status": "APPROVED", "values": {}},
            parameter_status="APPROVED",
            result_status="evaluated",
            raw_x=Decimal("3"),
            score=Decimal("0.7500"),
            step_trace=[],
            transactions=[transaction],
            alert_mode="ALERT",
        )
        evaluation = DetectionEvaluation(
            results=[result],
            summary={"rules": {"R01": {"alerts": 1}}},
        )
        rule = SimpleNamespace(rule_id=5, weight=Decimal("1.000"))
        session = UniqueAlertSession()
        repository = SqlAlchemyDetectionRepository(session)

        first = repository.persist_run(
            uuid4(),
            AS_OF,
            evaluation,
            {"R01": rule},
        )
        second = repository.persist_run(
            uuid4(),
            AS_OF,
            evaluation,
            {"R01": rule},
        )

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(len(session.alert_keys), 1)


if __name__ == "__main__":
    unittest.main()
