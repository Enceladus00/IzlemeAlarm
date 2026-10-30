import logging
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from backend.detection.engine import DetectionEngine
from backend.detection.evidence import (
    alert_severity,
    daily_deduplication_key,
    deduplication_key,
)
from backend.detection.evaluation import DetectionEvaluation
from backend.detection.metadata import DetectionContext, RuleResultEvidence
from backend.detection.parameters import validate_rule_parameters
from backend.detection.registry import load_rule_registry
from backend.detection.rules.r01_splitting import SplittingRule
from backend.detection.rules.r02_large_single import LargeSingleTransactionRule
from backend.detection.rules.r03_cash_deposits import CashDepositsRule
from backend.detection.rules.r04_income_volume import IncomeVolumeRule
from backend.detection.rules.r05_unusual_amount import UnusualAmountRule
from backend.detection.rules.r06_velocity import VelocityIncreaseRule
from backend.detection.rules.r07_dormant_account import DormantAccountRule
from backend.detection.rules.r08_new_account import NewAccountActivityRule
from backend.detection.rules.r09_cash_intensity import CashIntensityRule
from backend.detection.rules.r10_pass_through import PassThroughRule
from backend.detection.rules.r11_fan_in import FanInRule
from backend.detection.rules.r12_fan_out import FanOutRule
from backend.detection.rules.r13_layering import LayeringChainRule
from backend.detection.rules.r14_cycles import CyclePingPongRule
from backend.detection.rules.r15_suspicious_contact import SuspiciousContactRule
from backend.detection.rules.common import distribution_survival
from backend.detection.scoring import calculate_score
from backend.demo import (
    DEMO_RULE_OVERRIDES,
    DEMO_SCENARIOS,
    _scenario_transactions,
)
from backend.models import Alert, AlertTransaction, RuleResult
from backend.repositories.detection_repository import SqlAlchemyDetectionRepository


AS_OF = datetime(2026, 1, 8, 12)


def make_customer(
    customer_id: int,
    customer_type: str = "BIREYSEL",
    income: str | None = "1000",
    account_ids: list[int] | None = None,
    opened_at: date | None = date(2020, 1, 1),
) -> SimpleNamespace:
    return SimpleNamespace(
        customer_id=customer_id,
        customer_type=customer_type,
        monthly_income=Decimal(income) if income is not None else None,
        accounts=[
            SimpleNamespace(
                account_id=account_id,
                is_active=True,
                opened_at=opened_at,
            )
            for account_id in account_ids or []
        ],
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
        "window_days": 7,
        "band_low": "0.9",
        "above_check": "1.1",
        **overrides,
    }


def r03_values(**overrides: object) -> dict[str, object]:
    return {
        "limits": {"TRY": "100"},
        "x_esik": "1",
        "x_kesin": "3",
        "cash_channels": ["atm", "branch"],
        "window_days": 7,
        **overrides,
    }


def rule_rows(active_code: str | None = None, thresholds=None):
    rows = {
        code: SimpleNamespace(
            rule_code=code,
            is_active=code == active_code,
            thresholds=thresholds if code == active_code else {},
        )
        for code in (f"R{number:02d}" for number in range(1, 16))
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
        self.assertEqual(
            limit_result.step_trace[2]["details"]["upper_band_transaction_count"], 1
        )
        self.assertTrue(limit_result.force_zero)
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

    def test_r01_uses_configured_band_and_exclusive_upper_check(self) -> None:
        values = r01_values(band_low="0.8", above_check="1.2")
        transactions = [
            make_transaction(1, "80", sender_id=1),
            make_transaction(2, "119.99", sender_id=1),
            make_transaction(3, "120", sender_id=1),
        ]
        result = SplittingRule().evaluate_raw(
            [make_customer(1)],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("1"))
        self.assertTrue(result.force_zero)
        self.assertEqual([tx.transaction_id for tx in result.transactions], [1])
        self.assertEqual(
            result.step_trace[2]["details"]["upper_band_transaction_count"], 1
        )

    def test_r01_excludes_own_account_transfers_and_suppresses_missing_income(self) -> None:
        transactions = [
            make_transaction(1, "95", sender_id=1, receiver_id=1),
            make_transaction(2, "95", sender_id=1, receiver_id=2),
        ]
        result = SplittingRule().evaluate_raw(
            [make_customer(1, income=None)],
            transactions,
            {"BIREYSEL": parameter_set(r01_values())},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("1"))
        self.assertTrue(result.force_zero)
        self.assertEqual([tx.transaction_id for tx in result.transactions], [2])
        self.assertTrue(
            result.step_trace[2]["details"]["analyst_review_required"]
        )

    def test_r01_excludes_transactions_outside_calendar_window(self) -> None:
        values = r01_values(window_days=2)
        transactions = [
            make_transaction(
                1, "95", sender_id=1, tx_time=AS_OF - timedelta(days=2)
            ),
            make_transaction(
                2, "95", sender_id=1, tx_time=AS_OF - timedelta(days=1)
            ),
        ]
        result = SplittingRule().evaluate_raw(
            [make_customer(1)],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("1"))
        self.assertEqual([tx.transaction_id for tx in result.transactions], [2])

    def test_r02_amount_equal_to_limit_scores_one(self) -> None:
        values = {"limits": {"TRY": "100"}}
        result = LargeSingleTransactionRule().evaluate_raw(
            [make_customer(1)],
            [
                make_transaction(
                    1, "100", sender_id=1, tx_time=AS_OF - timedelta(hours=1)
                )
            ],
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(
            calculate_score(result.raw_x, binary_limit=result.binary_limit),
            Decimal("1.0000"),
        )
        self.assertEqual(result.transactions[0].transaction_id, 1)

    def test_r02_is_run_date_scoped_and_keeps_all_qualifying_evidence(self) -> None:
        transactions = [
            make_transaction(
                1, "100", sender_id=1, tx_time=AS_OF - timedelta(hours=2)
            ),
            make_transaction(
                2, "200", sender_id=1, tx_time=AS_OF - timedelta(hours=1)
            ),
            make_transaction(3, "300", sender_id=1, tx_time=AS_OF - timedelta(days=1)),
            make_transaction(4, "400", sender_id=1, tx_time=AS_OF),
        ]
        result = LargeSingleTransactionRule().evaluate_raw(
            [make_customer(1)],
            transactions,
            {"BIREYSEL": parameter_set({"limits": {"TRY": "100"}})},
            as_of=AS_OF,
        )[0]
        self.assertEqual([tx.transaction_id for tx in result.transactions], [1, 2])
        self.assertEqual(result.binary_limit, Decimal("100"))

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

    def test_r03_uses_configured_window_and_excludes_internal_transfers(self) -> None:
        transactions = [
            make_transaction(
                1,
                "50",
                sender_id=1,
                receiver_id=2,
                receiver_account_id=22,
                channel="atm",
            ),
            make_transaction(
                2,
                "50",
                sender_id=2,
                receiver_id=2,
                receiver_account_id=22,
                channel="atm",
            ),
            make_transaction(
                3,
                "50",
                sender_id=1,
                receiver_id=2,
                receiver_account_id=22,
                channel="atm",
                tx_time=AS_OF - timedelta(days=2),
            ),
        ]
        result = CashDepositsRule().evaluate_raw(
            [make_customer(2)],
            transactions,
            {"BIREYSEL": parameter_set(r03_values(window_days=2))},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("1"))
        self.assertEqual([tx.transaction_id for tx in result.transactions], [1])

    def test_parameters_are_selected_by_customer_type_and_trace_is_persistable(self) -> None:
        thresholds = {
            "BIREYSEL": parameter_set({"limits": {"TRY": "50"}}),
            "KURUMSAL": parameter_set({"limits": {"TRY": "100"}}),
        }
        customers = [make_customer(1, "BIREYSEL"), make_customer(2, "KURUMSAL")]
        transaction = make_transaction(
            1, "75", sender_id=1, receiver_id=2, tx_time=AS_OF - timedelta(hours=1)
        )
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
        transaction = make_transaction(
            1, "100", sender_id=1, tx_time=AS_OF - timedelta(hours=1)
        )
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
            make_transaction(
                103,
                "16000",
                sender_id=2,
                receiver_id=1,
                tx_time=AS_OF - timedelta(hours=1),
            ),
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
        self.assertEqual(results[("R02", 2)].alert_mode, "ALERT")
        self.assertEqual(results[("R03", 3)].score, Decimal("0.9000"))
        self.assertEqual([tx.transaction_id for tx in results[("R03", 3)].transactions], [104, 105, 106])

    def test_demo_fixture_exercises_all_fifteen_rule_scenarios(self) -> None:
        customers = []
        accounts = []
        for customer_id in range(1, 25):
            customer = SimpleNamespace(
                customer_id=customer_id,
                customer_type="BIREYSEL" if customer_id <= 3 else "KURUMSAL",
                monthly_income=Decimal("50000"),
                accounts=[],
            )
            account = SimpleNamespace(
                account_id=customer_id,
                customer_id=customer_id,
                is_active=True,
                opened_at=AS_OF.date()
                - timedelta(days=14 if customer_id == 8 else 365),
                customer=customer,
            )
            customer.accounts.append(account)
            customers.append(customer)
            accounts.append(account)

        transactions = [
            SimpleNamespace(
                transaction_id=transaction_id,
                transaction_no=number,
                sender_account_id=sender_id,
                receiver_account_id=receiver_id,
                sender_account=accounts[sender_id - 1],
                receiver_account=accounts[receiver_id - 1],
                amount=Decimal(amount),
                currency="TRY",
                tx_time=tx_time,
                channel=channel,
            )
            for transaction_id, (
                number,
                sender_id,
                receiver_id,
                amount,
                tx_time,
                channel,
            ) in enumerate(_scenario_transactions(AS_OF), 1)
        ]
        evaluation = DetectionEngine().evaluate(
            customers,
            transactions,
            rule_rows(),
            as_of=AS_OF,
            rule_overrides=DEMO_RULE_OVERRIDES,
            context=DetectionContext(
                suspicious_customer_ids_by_status={"confirmed_suspicious": {22}},
                suspicious_account_ids_by_status={"confirmed_suspicious": {22}},
            ),
        )
        results = {
            (result.rule_code, result.customer_id): result
            for result in evaluation.results
        }

        self.assertEqual(len(DEMO_SCENARIOS), 15)
        self.assertEqual(
            {scenario[0] for scenario in DEMO_SCENARIOS},
            set(DEMO_RULE_OVERRIDES),
        )
        self.assertEqual(evaluation.summary["transaction_count"], 80)
        for rule_code, customer_no, _account_no, _intent in DEMO_SCENARIOS:
            result = results[(rule_code, int(customer_no[-3:]))]
            self.assertEqual(result.result_status, "evaluated", rule_code)
            self.assertGreaterEqual(result.score, Decimal("0.5"), rule_code)
            self.assertGreater(
                evaluation.summary["rules"][rule_code]["elapsed_ms"], 0
            )

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

    def test_new_rule_parameters_validate_with_legacy_defaults_and_reject_bad_bands(self) -> None:
        legacy_r01 = r01_values()
        del legacy_r01["window_days"]
        del legacy_r01["band_low"]
        del legacy_r01["above_check"]
        validated_r01 = validate_rule_parameters(
            "R01",
            SplittingRule.definition.parameter_model,
            {
                "BIREYSEL": parameter_set(legacy_r01),
                "KURUMSAL": {"status": "UNSET", "values": {}},
            },
        )
        self.assertEqual(
            validated_r01["BIREYSEL"]["values"]["window_days"], 7
        )
        self.assertEqual(validated_r01["BIREYSEL"]["values"]["band_low"], "0.9")
        self.assertEqual(
            validated_r01["BIREYSEL"]["values"]["above_check"], "1.1"
        )

        invalid_band = r01_values(band_low="1")
        with self.assertRaises(ValueError):
            validate_rule_parameters(
                "R01",
                SplittingRule.definition.parameter_model,
                {
                    "BIREYSEL": parameter_set(invalid_band),
                    "KURUMSAL": {"status": "UNSET", "values": {}},
                },
            )

    def test_registry_rejects_missing_rule_rows_and_active_implementations(self) -> None:
        registry = load_rule_registry()
        self.assertEqual(set(registry), {f"R{number:02d}" for number in range(1, 16)})
        missing_rule_row = rule_rows()
        del missing_rule_row["R03"]
        with self.assertRaisesRegex(RuntimeError, "implementations_without_database_row"):
            DetectionEngine().evaluate([], [], missing_rule_row, as_of=AS_OF)
        unknown = rule_rows()
        unknown["R16"] = SimpleNamespace(
            rule_code="R16", is_active=True, thresholds={}
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
            1,
            "500",
            sender_id=1,
            currency="USD",
            tx_time=AS_OF - timedelta(hours=1),
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

    def test_r04_alerts_from_aggregate_volume_without_transaction_evidence(self) -> None:
        values = {
            "window_days": 7,
            "x_esik": "0.1",
            "x_kesin": "0.5",
        }
        transaction = make_transaction(
            401, "200", sender_id=2, receiver_id=1
        )
        raw = IncomeVolumeRule().evaluate_raw(
            [make_customer(1, income="1000")],
            [transaction],
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(raw.raw_x, Decimal("0.2"))
        self.assertEqual(raw.transactions, [])
        self.assertFalse(raw.force_zero)

        thresholds = {
            "BIREYSEL": parameter_set(values),
            "KURUMSAL": {"status": "UNSET", "values": {}},
        }
        evaluation = DetectionEngine().evaluate(
            [make_customer(1, income="1000")],
            [transaction],
            rule_rows("R04", thresholds),
            as_of=AS_OF,
        )
        self.assertGreaterEqual(evaluation.results[0].score, Decimal("0.5"))
        self.assertEqual(evaluation.summary["rules"]["R04"]["alerts"], 1)

    def test_r05_uses_history_and_ignores_internal_transfers(self) -> None:
        rule = UnusualAmountRule()
        customer = make_customer(1, income="1000")
        values = {
            "history_days": 10,
            "kappa": "1",
            "mad_floor": "0.1",
            "income_bands": 2,
            "x_esik": "1",
            "x_kesin": "3",
        }
        transactions = [
            make_transaction(501, "100", sender_id=1, tx_time=AS_OF - timedelta(days=3)),
            make_transaction(502, "100", sender_id=2, receiver_id=1, tx_time=AS_OF - timedelta(days=2)),
            make_transaction(503, "1000", sender_id=1, tx_time=AS_OF - timedelta(hours=1)),
            make_transaction(
                504,
                "9000",
                sender_id=1,
                receiver_id=1,
                tx_time=AS_OF - timedelta(minutes=30),
            ),
            make_transaction(
                505,
                "1000000",
                sender_id=1,
                currency="USD",
                tx_time=AS_OF - timedelta(minutes=15),
            ),
        ]
        result = rule.evaluate_raw(
            [customer],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual([tx.transaction_id for tx in result.transactions], [503])
        self.assertEqual(result.step_trace[1]["details"]["currency"], "TRY")
        self.assertFalse(result.force_zero)
        self.assertGreater(result.raw_x, Decimal("0"))

    def test_r06_counts_completed_weeks_and_respects_minimum_count(self) -> None:
        values = {
            "history_weeks": 2,
            "min_count": 2,
            "season_factor": {},
            "x_esik": "1",
            "x_kesin": "3",
        }
        customer = make_customer(1)
        current = [
            make_transaction(
                601,
                "10",
                sender_id=1,
                tx_time=AS_OF - timedelta(hours=2),
            ),
            make_transaction(
                602,
                "10",
                sender_id=1,
                tx_time=AS_OF - timedelta(hours=1),
            ),
        ]
        result = VelocityIncreaseRule().evaluate_raw(
            [customer],
            current,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertGreater(result.raw_x, Decimal("1"))
        self.assertFalse(result.force_zero)
        self.assertEqual(len(result.transactions), 2)
        self.assertEqual(
            result.step_trace[0]["details"]["current_week_count"], 2
        )

        probability = distribution_survival(3, mean=1.0, variance=1.0)
        self.assertGreater(probability, 0)
        self.assertLess(probability, 1)
        negative_binomial_probability = distribution_survival(
            3, mean=2.0, variance=5.0
        )
        self.assertGreater(negative_binomial_probability, 0)
        self.assertLess(negative_binomial_probability, 1)

    def test_r07_requires_a_dormancy_gap_and_uses_account_limit(self) -> None:
        values = {
            "dormant_days": 5,
            "window_days": 2,
            "limits": {"TRY": "100"},
            "x_esik": "0",
            "x_kesin": "1",
            "cash_accounts": [],
        }
        transactions = [
            make_transaction(
                701,
                "50",
                sender_id=1,
                sender_account_id=11,
                tx_time=AS_OF - timedelta(days=10),
            ),
            make_transaction(
                702,
                "200",
                sender_id=1,
                sender_account_id=11,
                tx_time=AS_OF - timedelta(days=1),
            ),
        ]
        result = DormantAccountRule().evaluate_raw(
            [make_customer(1, account_ids=[11])],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("2").ln())
        self.assertEqual([tx.transaction_id for tx in result.transactions], [702])

    def test_r08_scores_only_transactions_after_new_account_opening(self) -> None:
        values = {
            "account_age_days": 30,
            "limits": {"TRY": "100"},
            "x_esik": "0",
            "x_kesin": "1",
        }
        transaction = make_transaction(
            801,
            "200",
            sender_id=1,
            sender_account_id=11,
            tx_time=AS_OF - timedelta(days=1),
        )
        result = NewAccountActivityRule().evaluate_raw(
            [make_customer(1, account_ids=[11], opened_at=AS_OF.date() - timedelta(days=5))],
            [transaction],
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("2").ln())
        self.assertEqual(result.transactions, [transaction])

    def test_r09_compares_current_cash_share_with_prior_period(self) -> None:
        values = {
            "window_days": 2,
            "baseline_days": 2,
            "cash_channels": ["atm"],
            "limits": {"TRY": "20"},
            "x_esik": "0.1",
            "x_kesin": "0.5",
        }
        customer = make_customer(1, account_ids=[11])
        transactions = [
            make_transaction(
                901,
                "10",
                sender_id=2,
                receiver_id=1,
                sender_account_id=22,
                receiver_account_id=11,
                channel="atm",
                tx_time=AS_OF - timedelta(days=2),
            ),
            make_transaction(
                902,
                "90",
                sender_id=2,
                receiver_id=1,
                sender_account_id=22,
                receiver_account_id=11,
                channel="internet",
                tx_time=AS_OF - timedelta(days=2),
            ),
            make_transaction(
                903,
                "50",
                sender_id=2,
                receiver_id=1,
                sender_account_id=22,
                receiver_account_id=11,
                channel="atm",
                tx_time=AS_OF - timedelta(days=1),
            ),
            make_transaction(
                904,
                "50",
                sender_id=2,
                receiver_id=1,
                sender_account_id=22,
                receiver_account_id=11,
                channel="internet",
                tx_time=AS_OF - timedelta(days=1),
            ),
        ]
        result = CashIntensityRule().evaluate_raw(
            [customer],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("0.4"))
        self.assertEqual([tx.transaction_id for tx in result.transactions], [903])

    def test_r10_requires_volume_and_ratio_then_scores_new_recipient_share(self) -> None:
        values = {
            "window_hours": 24,
            "limits": {"TRY": "50"},
            "ratio_low": "0.5",
            "ratio_high": "1",
            "cash_accounts": [],
            "x_esik": "0.5",
            "x_kesin": "1",
        }
        transactions = [
            make_transaction(
                1001,
                "100",
                sender_id=2,
                receiver_id=1,
                sender_account_id=22,
                receiver_account_id=11,
                tx_time=AS_OF - timedelta(hours=20),
            ),
            make_transaction(
                1002,
                "80",
                sender_id=1,
                receiver_id=3,
                sender_account_id=11,
                receiver_account_id=33,
                tx_time=AS_OF - timedelta(hours=18),
            ),
        ]
        result = PassThroughRule().evaluate_raw(
            [make_customer(1, account_ids=[11])],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("1"))
        self.assertEqual({tx.transaction_id for tx in result.transactions}, {1001, 1002})

    def test_r11_counts_unique_new_sender_accounts(self) -> None:
        values = {
            "window_days": 7,
            "cash_accounts": [],
            "x_esik": "1",
            "x_kesin": "3",
        }
        transactions = [
            make_transaction(
                1101,
                "10",
                sender_id=2,
                receiver_id=1,
                sender_account_id=22,
                receiver_account_id=11,
            ),
            make_transaction(
                1102,
                "20",
                sender_id=3,
                receiver_id=1,
                sender_account_id=33,
                receiver_account_id=11,
            ),
        ]
        result = FanInRule().evaluate_raw(
            [make_customer(1, account_ids=[11])],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("2"))
        self.assertEqual(len(result.transactions), 2)

    def test_r12_applies_currency_scoped_equal_amount_multiplier(self) -> None:
        values = {
            "window_days": 7,
            "cash_accounts": [],
            "cv_threshold": "0.1",
            "cv_multiplier": "2",
            "x_esik": "1",
            "x_kesin": "4",
        }
        transactions = [
            make_transaction(
                1201,
                "100",
                sender_id=1,
                receiver_id=2,
                sender_account_id=11,
                receiver_account_id=22,
            ),
            make_transaction(
                1202,
                "100",
                sender_id=1,
                receiver_id=3,
                sender_account_id=11,
                receiver_account_id=33,
            ),
        ]
        result = FanOutRule().evaluate_raw(
            [make_customer(1, account_ids=[11])],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("4"))
        self.assertEqual(len(result.transactions), 2)

    def test_r13_finds_time_ordered_decreasing_external_chain(self) -> None:
        values = {
            "window_days": 7,
            "max_step_hours": 24,
            "decay_low": "0.7",
            "decay_high": "0.9",
            "max_depth": 4,
            "cash_accounts": [],
            "x_esik": "1",
            "x_kesin": "3",
        }
        transactions = [
            make_transaction(
                1301,
                "100",
                sender_id=1,
                receiver_id=2,
                sender_account_id=11,
                receiver_account_id=22,
                tx_time=AS_OF - timedelta(hours=3),
            ),
            make_transaction(
                1302,
                "80",
                sender_id=2,
                receiver_id=3,
                sender_account_id=22,
                receiver_account_id=33,
                tx_time=AS_OF - timedelta(hours=2),
            ),
        ]
        result = LayeringChainRule().evaluate_raw(
            [make_customer(1, account_ids=[11])],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )[0]
        self.assertEqual(result.raw_x, Decimal("2"))
        self.assertEqual([tx.transaction_id for tx in result.transactions], [1301, 1302])

    def test_r14_detects_a_time_ordered_same_currency_cycle(self) -> None:
        values = {
            "window_days": 7,
            "max_cycle_length": 5,
            "min_retained": "0.8",
            "pingpong_tolerance": "0.05",
            "cash_accounts": [],
            "x_esik": "1",
            "x_kesin": "3",
        }
        customers = [
            make_customer(1, account_ids=[11]),
            make_customer(2, account_ids=[22]),
            make_customer(3, account_ids=[33]),
        ]
        transactions = [
            make_transaction(
                1401,
                "100",
                sender_id=1,
                receiver_id=2,
                sender_account_id=11,
                receiver_account_id=22,
                tx_time=AS_OF - timedelta(hours=3),
            ),
            make_transaction(
                1402,
                "95",
                sender_id=2,
                receiver_id=3,
                sender_account_id=22,
                receiver_account_id=33,
                tx_time=AS_OF - timedelta(hours=2),
            ),
            make_transaction(
                1403,
                "90",
                sender_id=3,
                receiver_id=1,
                sender_account_id=33,
                receiver_account_id=11,
                tx_time=AS_OF - timedelta(hours=1),
            ),
        ]
        results = CyclePingPongRule().evaluate_raw(
            customers,
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )
        self.assertTrue(all(result.score_override == Decimal("1") for result in results))
        self.assertTrue(all(len(result.transactions) == 3 for result in results))

    def test_r14_counts_pingpong_pairs_once_and_uses_tolerance(self) -> None:
        values = {
            "window_days": 7,
            "max_cycle_length": 5,
            "min_retained": "0.8",
            "pingpong_tolerance": "0.02",
            "cash_accounts": [],
            "x_esik": 1,
            "x_kesin": 3,
        }
        transactions = [
            make_transaction(
                1411,
                "100",
                sender_id=1,
                receiver_id=2,
                sender_account_id=11,
                receiver_account_id=22,
                tx_time=AS_OF - timedelta(hours=2),
            ),
            make_transaction(
                1412,
                "99",
                sender_id=2,
                receiver_id=1,
                sender_account_id=22,
                receiver_account_id=11,
                tx_time=AS_OF - timedelta(hours=1),
            ),
        ]
        result = CyclePingPongRule().evaluate_raw(
            [make_customer(1, account_ids=[11]), make_customer(2, account_ids=[22])],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
        )
        self.assertEqual([item.raw_x for item in result], [Decimal("1"), Decimal("1")])
        self.assertEqual(
            [item.score_override for item in result],
            [Decimal("0.5000"), Decimal("0.5000")],
        )
        self.assertTrue(all(len(item.transactions) == 2 for item in result))

    def test_r15_scores_direct_confirmed_suspicious_account_contact(self) -> None:
        from backend.detection.metadata import DetectionContext

        values = {
            "window_days": 7,
            "suspicious_status": "confirmed_suspicious",
            "gamma": "0.5",
            "cash_accounts": [],
        }
        transaction = make_transaction(
            1501,
            "10",
            sender_id=1,
            receiver_id=2,
            sender_account_id=11,
            receiver_account_id=22,
        )
        result = SuspiciousContactRule().evaluate_raw(
            [make_customer(1, account_ids=[11])],
            [transaction],
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
            context=DetectionContext(
                suspicious_customer_ids_by_status={"confirmed_suspicious": {2}},
                suspicious_account_ids_by_status={"confirmed_suspicious": {22}},
            ),
        )[0]
        self.assertEqual(result.score_override, Decimal("1"))
        self.assertEqual(result.transactions, [transaction])

    def test_r15_scores_contact_through_one_intermediary_with_gamma(self) -> None:
        from backend.detection.metadata import DetectionContext

        values = {
            "window_days": 7,
            "suspicious_status": "confirmed_suspicious",
            "gamma": "0.4",
            "cash_accounts": [],
        }
        transactions = [
            make_transaction(
                1511,
                "10",
                sender_id=1,
                receiver_id=2,
                sender_account_id=11,
                receiver_account_id=22,
            ),
            make_transaction(
                1512,
                "20",
                sender_id=2,
                receiver_id=3,
                sender_account_id=22,
                receiver_account_id=33,
            ),
        ]
        result = SuspiciousContactRule().evaluate_raw(
            [make_customer(1, account_ids=[11])],
            transactions,
            {"BIREYSEL": parameter_set(values)},
            as_of=AS_OF,
            context=DetectionContext(
                suspicious_customer_ids_by_status={"confirmed_suspicious": {3}},
                suspicious_account_ids_by_status={"confirmed_suspicious": {33}},
            ),
        )[0]
        self.assertEqual(result.score_override, Decimal("0.4"))
        self.assertEqual({tx.transaction_id for tx in result.transactions}, {1511, 1512})

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
        self.assertEqual(
            daily_deduplication_key("R01", 42, AS_OF.date()),
            "R01:42:2026-01-08",
        )
        self.assertEqual(alert_severity(Decimal("0.9000")), "high")
        self.assertEqual(alert_severity(Decimal("0.7000")), "medium")
        self.assertEqual(alert_severity(Decimal("0.5000")), "low")

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
                self.alert_rows = {}
                self.alert_values = []
                self.alert_transaction_values = []
                self.next_result_id = 1
                self.next_alert_id = 1

            def add(self, value):
                self.pending.append(value)

            def add_all(self, values):
                self.pending.extend(values)

            def scalars(self, _statement):
                return SimpleNamespace(
                    all=lambda: list(self.alert_rows.values())
                )

            def flush(self):
                for value in self.pending:
                    if isinstance(value, RuleResult) and value.result_id is None:
                        value.result_id = self.next_result_id
                        self.next_result_id += 1

            def execute(self, statement):
                if statement.table.name != Alert.__tablename__:
                    if statement.table.name == AlertTransaction.__tablename__:
                        self.alert_transaction_values.extend(statement._multi_values[0])
                    return FakeResult()
                inserted = []
                for row in statement._multi_values[0]:
                    key = row[Alert.__table__.c.deduplication_key]
                    if key not in self.alert_keys:
                        alert_id = self.next_alert_id
                        self.next_alert_id += 1
                        self.alert_keys[key] = alert_id
                        inserted.append((alert_id, key))
                        self.alert_values.append(row)
                        self.alert_rows[key] = SimpleNamespace(
                            deduplication_key=key,
                            alert_id=alert_id,
                            score=row[Alert.__table__.c.score],
                            severity=row[Alert.__table__.c.severity],
                        )
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
        later_transaction = make_transaction(92, "20")
        later_result = RuleResultEvidence(
            rule_code="R01",
            customer_id=1,
            customer_type="BIREYSEL",
            parameter_snapshot={"status": "APPROVED", "values": {}},
            parameter_status="APPROVED",
            result_status="evaluated",
            raw_x=Decimal("3"),
            score=Decimal("0.9000"),
            step_trace=[],
            transactions=[later_transaction],
            alert_mode="ALERT",
        )
        later_evaluation = DetectionEvaluation(
            results=[later_result],
            summary={"rules": {"R01": {"alerts": 1}}},
        )
        second = repository.persist_run(
            uuid4(),
            AS_OF,
            later_evaluation,
            {"R01": rule},
        )

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(len(session.alert_keys), 1)
        self.assertEqual(
            session.alert_values[0][Alert.__table__.c.severity], "medium"
        )
        self.assertEqual(
            session.alert_rows["R01:1:2026-01-08"].score, Decimal("0.9000")
        )
        self.assertEqual(session.alert_rows["R01:1:2026-01-08"].severity, "high")
        self.assertEqual(
            {
                row[AlertTransaction.__table__.c.transaction_id]
                for row in session.alert_transaction_values
            },
            {91, 92},
        )

        aggregate_session = UniqueAlertSession()
        aggregate_result = RuleResultEvidence(
            rule_code="R04",
            customer_id=7,
            customer_type="BIREYSEL",
            parameter_snapshot={"status": "APPROVED", "values": {}},
            parameter_status="APPROVED",
            result_status="evaluated",
            raw_x=Decimal("0.8"),
            score=Decimal("0.7500"),
            step_trace=[],
            transactions=[],
            alert_mode="ALERT",
        )
        aggregate_created = SqlAlchemyDetectionRepository(
            aggregate_session
        ).persist_run(
            uuid4(),
            AS_OF,
            DetectionEvaluation(
                results=[aggregate_result],
                summary={"rules": {"R04": {"alerts": 1}}},
            ),
            {"R04": SimpleNamespace(rule_id=8, weight=Decimal("1.000"))},
        )
        self.assertEqual(aggregate_created, 1)
        self.assertEqual(len(aggregate_session.alert_values), 1)
        self.assertEqual(aggregate_session.alert_transaction_values, [])


if __name__ == "__main__":
    unittest.main()
