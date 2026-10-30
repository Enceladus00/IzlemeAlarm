from datetime import datetime
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.orm import configure_mappers

from backend.db_url import normalize_database_url
from backend.detection.evaluation import DetectionEvaluation
from backend.detection.registry import load_rule_registry
from backend.main import app
from backend.models import AlertStatusHistory, AuditLog, Base, RuleChangeLog
from backend.repositories.alert_repository import SqlAlchemyAlertRepository
from backend.repositories.transaction_repository import (
    SqlAlchemyTransactionRepository,
    TransactionFilters,
)
from backend.repositories.rule_repository import SqlAlchemyRuleRepository
from backend.rules import _dedup
from backend.services.alert_service import AlertService
from backend.services.demo_service import DemoService
from backend.services.detection_service import DetectionService
from backend.services.rule_service import (
    InvalidRuleThresholds,
    RuleService,
    validate_thresholds,
)


class ApplicationTests(unittest.TestCase):
    def test_api_routes_are_composed_without_duplicate_handlers(self) -> None:
        paths = app.openapi()["paths"]
        operations = [
            (method, path)
            for path, path_operations in paths.items()
            for method in path_operations
        ]
        required_paths = {
            "/health",
            "/auth/login",
            "/auth/me",
            "/dashboard/summary",
            "/alerts",
            "/alerts/{alert_id}",
            "/alerts/{alert_id}/status",
            "/transactions",
            "/customers/{customer_no}/transactions",
            "/rules",
            "/rules/{rule_code}",
            "/rules/evaluate",
            "/demo/seed",
            "/demo/status",
            "/uploads",
            "/uploads/{batch_id}",
            "/audit-log",
            "/users",
        }
        self.assertTrue(required_paths.issubset(paths))
        self.assertEqual(len(operations), len(set(operations)))

    def test_transactions_can_be_filtered_to_an_account_direction(self) -> None:
        statements: list[object] = []

        class EmptyScalars:
            def __iter__(self):
                return iter(())

            def unique(self) -> "EmptyScalars":
                return self

            def all(self) -> list[object]:
                return []

        class QueryCaptureSession:
            def scalar(self, statement: object) -> int:
                return 0

            def scalars(self, statement: object) -> EmptyScalars:
                statements.append(statement)
                return EmptyScalars()

        SqlAlchemyTransactionRepository(QueryCaptureSession()).list_transactions(
            TransactionFilters(account_no="ACC-42", direction="incoming")
        )

        statement = statements[0]
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("ACC-42", sql)
        self.assertIn("receiver_account_id IN", sql)

    def test_analyst_note_is_saved_without_changing_alert_status(self) -> None:
        alert = SimpleNamespace(alert_id=12, status="in_review")
        records: list[object] = []
        session = SimpleNamespace(
            get=lambda _model, _alert_id: alert,
            add=records.append,
            commit=lambda: None,
        )

        result = AlertService(SqlAlchemyAlertRepository(session)).update_status(
            12,
            "in_review",
            "Reviewed account activity.",
            actor_id=7,
        )

        history = next(record for record in records if isinstance(record, AlertStatusHistory))
        audit = next(record for record in records if isinstance(record, AuditLog))
        self.assertEqual(result, {"alert_id": 12, "status": "in_review", "changed": False})
        self.assertEqual(history.old_status, "in_review")
        self.assertEqual(history.new_status, "in_review")
        self.assertEqual(history.changed_by, 7)
        self.assertEqual(history.note, "Reviewed account activity.")
        self.assertEqual(audit.action, "alert.note_added")

    def test_entity_relationships_configure(self) -> None:
        configure_mappers()
        self.assertIn("customer", Base.metadata.tables)
        self.assertIn("transaction", Base.metadata.tables)
        self.assertIn("alert_status_history", Base.metadata.tables)
        self.assertIn("detection_run", Base.metadata.tables)
        self.assertIn("rule_result", Base.metadata.tables)
        self.assertIn("rule_result_transaction", Base.metadata.tables)

    def test_rule_thresholds_are_validated_by_customer_type(self) -> None:
        normalized = validate_thresholds(
            "R01",
            {
                "BIREYSEL": {
                    "status": "PROVISIONAL",
                    "values": {
                        "limits": {"TRY": "10000"},
                        "x_esik": 2,
                        "x_kesin": 5,
                        "minimum_income_ratio": "0.01",
                        "income_currency": "TRY",
                    },
                },
                "KURUMSAL": {"status": "UNSET", "values": {}},
            },
        )
        self.assertEqual(
            normalized["BIREYSEL"]["values"]["limits"]["TRY"],
            "10000",
        )
        self.assertEqual(normalized["KURUMSAL"]["status"], "UNSET")

    def test_r03_thresholds_accept_currency_map_and_report_invalid_fields(self) -> None:
        correct_shape = {
            customer_type: {
                "status": "PROVISIONAL",
                "values": {
                    "limits": {"USD": 50000.00},
                    "x_esik": 3,
                    "x_kesin": 5,
                    "cash_channels": ["atm", "branch"],
                },
            }
            for customer_type in ("BIREYSEL", "KURUMSAL")
        }
        normalized = validate_thresholds("R03", correct_shape)
        self.assertEqual(
            normalized["BIREYSEL"]["values"]["limits"]["USD"], "50000.0"
        )

        invalid_shape = {
            **correct_shape,
            "BIREYSEL": {
                "status": "PROVISIONAL",
                "values": {
                    "limits": 50000.00,
                    "x_esik": 3,
                    "x_kesin": 5,
                },
            },
        }
        with self.assertRaises(InvalidRuleThresholds) as raised:
            validate_thresholds("R03", invalid_shape)
        self.assertIn("R03", str(raised.exception))
        self.assertIn("limits", str(raised.exception))
        self.assertIn("cash_channels", str(raised.exception))

    def test_r04_to_r15_parameter_models_accept_configurable_values(self) -> None:
        examples = {
            "R04": {"window_days": 7, "x_esik": "0.1", "x_kesin": "0.5"},
            "R05": {
                "history_days": 90,
                "kappa": "5",
                "mad_floor": "0.1",
                "income_bands": 5,
                "x_esik": "1",
                "x_kesin": "3",
            },
            "R06": {
                "history_weeks": 12,
                "min_count": 3,
                "season_factor": {"2026-01-11": "1.2"},
                "x_esik": "1",
                "x_kesin": "3",
            },
            "R07": {
                "dormant_days": 90,
                "window_days": 7,
                "limits": {"TRY": "1000"},
                "x_esik": "1",
                "x_kesin": "3",
            },
            "R08": {
                "account_age_days": 30,
                "limits": {"TRY": "1000"},
                "x_esik": "1",
                "x_kesin": "3",
            },
            "R09": {
                "window_days": 7,
                "baseline_days": 30,
                "cash_channels": ["atm", "branch"],
                "limits": {"TRY": "1000"},
                "x_esik": "0.1",
                "x_kesin": "0.5",
            },
            "R10": {
                "window_hours": 24,
                "limits": {"TRY": "1000"},
                "ratio_low": "0.5",
                "ratio_high": "1.2",
                "x_esik": "0.5",
                "x_kesin": "1",
            },
            "R11": {"window_days": 7, "x_esik": 1, "x_kesin": 3},
            "R12": {
                "window_days": 7,
                "cv_threshold": "0.2",
                "cv_multiplier": "2",
                "x_esik": 1,
                "x_kesin": 3,
            },
            "R13": {
                "window_days": 7,
                "max_step_hours": 24,
                "decay_low": "0.5",
                "decay_high": "0.9",
                "max_depth": 5,
                "x_esik": 2,
                "x_kesin": 5,
            },
            "R14": {
                "window_days": 7,
                "max_cycle_length": 5,
                "min_retained": "0.8",
                "pingpong_tolerance": "0.05",
                "x_esik": 1,
                "x_kesin": 3,
            },
            "R15": {
                "window_days": 7,
                "suspicious_status": "confirmed_suspicious",
                "gamma": "0.5",
            },
        }
        for rule_code, values in examples.items():
            thresholds = {
                customer_type: {
                    "status": "PROVISIONAL",
                    "values": values,
                }
                for customer_type in ("BIREYSEL", "KURUMSAL")
            }
            with self.subTest(rule_code=rule_code):
                normalized = validate_thresholds(rule_code, thresholds)
                self.assertEqual(normalized["BIREYSEL"]["status"], "PROVISIONAL")

    def test_every_rule_parameter_is_exposed_in_rule_metadata(self) -> None:
        for rule_code, strategy in load_rule_registry().items():
            model_fields = set(strategy.definition.parameter_model.model_fields)
            metadata_fields = {
                parameter.name for parameter in strategy.definition.parameters
            }
            with self.subTest(rule_code=rule_code):
                self.assertEqual(model_fields, metadata_fields)

    def test_rule_list_includes_feasibility_and_review_metadata(self) -> None:
        class FakeRuleRepository:
            def list_rules(self):
                return [
                    SimpleNamespace(
                        rule_code="R13",
                        name="legacy name",
                        description="legacy description",
                        is_active=False,
                        weight=Decimal("1.000"),
                        thresholds={},
                    )
                ]

        rule = RuleService(FakeRuleRepository()).list_rules()[0]
        self.assertEqual(rule["metadata"]["feasibility"], "LOW")
        self.assertTrue(rule["metadata"]["feasibility_reason"])
        self.assertTrue(rule["metadata"]["analyst_review_notes"])
        self.assertTrue(rule["metadata"]["parameters"])

    def test_detection_service_builds_suspicious_contact_context(self) -> None:
        class FakeRepository:
            def list_rules(self):
                return []

            def list_active_customers(self, _customer_ids):
                return []

            def list_active_transactions(self, _customer_ids=None):
                return []

            def list_customers_with_history_status(self, status):
                self.status = status
                return {22}

            def list_account_ids_for_customers(self, customer_ids):
                self.customer_ids = customer_ids
                return {2201, 2202}

            def persist_run(self, _run_id, _as_of, _evaluation, _rules, **_kwargs):
                self.evaluation = _evaluation
                return 0

        class CaptureEngine:
            def evaluate(self, *_args, **kwargs):
                self.context = kwargs["context"]
                return DetectionEvaluation(results=[], summary={})

        repository = FakeRepository()
        engine = CaptureEngine()
        self.assertEqual(DetectionService(repository, engine).evaluate(), 0)
        self.assertEqual(repository.status, "confirmed_suspicious")
        self.assertEqual(repository.customer_ids, {22})
        self.assertEqual(
            engine.context.suspicious_customer_ids_by_status[
                "confirmed_suspicious"
            ],
            {22},
        )
        self.assertEqual(
            engine.context.suspicious_account_ids_by_status[
                "confirmed_suspicious"
            ],
            {2201, 2202},
        )

    def test_rule_thresholds_reject_unsafe_or_ambiguous_values(self) -> None:
        invalid = [
            (
                "R01",
                {
                    "BIREYSEL": {
                        "status": "APPROVED",
                        "values": {
                            "limits": {"TRY": "100"},
                            "x_esik": 5,
                            "x_kesin": 3,
                            "minimum_income_ratio": "0.1",
                            "income_currency": "TRY",
                        },
                    },
                    "KURUMSAL": {"status": "UNSET", "values": {}},
                },
            ),
            (
                "R02",
                {
                    "BIREYSEL": {
                        "status": "APPROVED",
                        "values": {"limits": {"TRY": float("inf")}},
                    },
                    "KURUMSAL": {"status": "UNSET", "values": {}},
                },
            ),
            (
                "R03",
                {
                    "BIREYSEL": {
                        "status": "PROVISIONAL",
                        "values": {
                            "limits": {"TRY": "100"},
                            "x_esik": 1,
                            "x_kesin": 2,
                            "cash_channels": ["other"],
                        },
                    },
                    "KURUMSAL": {"status": "UNSET", "values": {}},
                },
            ),
            ("R01", {"BIREYSEL": {"status": "UNSET", "values": {}}}),
        ]
        for rule_code, thresholds in invalid:
            with self.subTest(rule_code=rule_code, thresholds=thresholds):
                with self.assertRaises(InvalidRuleThresholds):
                    validate_thresholds(rule_code, thresholds)

    def test_rule_activation_requires_at_least_one_configured_customer_type(self) -> None:
        class FakeRuleRepository:
            def __init__(self):
                self.saved = None

            def get_rule(self, rule_code):
                return SimpleNamespace(
                    rule_code=rule_code,
                    thresholds={
                        "BIREYSEL": {"status": "UNSET", "values": {}},
                        "KURUMSAL": {"status": "UNSET", "values": {}},
                    },
                    weight=Decimal("0.450"),
                    is_active=False,
                )

            def save_rule(self, rule, thresholds, is_active, weight, actor_id):
                self.saved = (thresholds, is_active)

        repository = FakeRuleRepository()
        service = RuleService(repository)
        unset_thresholds = {
            "BIREYSEL": {"status": "UNSET", "values": {}},
            "KURUMSAL": {"status": "UNSET", "values": {}},
        }
        with self.assertRaises(InvalidRuleThresholds):
            service.update_rule(
                "R02",
                unset_thresholds,
                True,
                actor_id=7,
            )

        configured_thresholds = {
            "BIREYSEL": {
                "status": "PROVISIONAL",
                "values": {"limits": {"TRY": "100"}},
            },
            "KURUMSAL": {"status": "UNSET", "values": {}},
        }
        service.update_rule(
            "R02",
            configured_thresholds,
            True,
            actor_id=7,
        )
        self.assertTrue(repository.saved[1])
        self.assertEqual(repository.saved[0]["KURUMSAL"]["status"], "UNSET")

    def test_weight_and_activation_changes_are_audited(self) -> None:
        records: list[object] = []
        session = SimpleNamespace(add=records.append, commit=lambda: None)
        rule = SimpleNamespace(
            rule_id=2,
            rule_code="R02",
            thresholds={"old": True},
            is_active=False,
            weight=Decimal("0.450"),
            updated_by=None,
            updated_at=None,
        )
        SqlAlchemyRuleRepository(session).save_rule(
            rule,
            {"new": True},
            True,
            Decimal("0.600"),
            actor_id=7,
        )
        change = next(row for row in records if isinstance(row, RuleChangeLog))
        audit = next(row for row in records if isinstance(row, AuditLog))
        self.assertEqual(change.old_thresholds, {"old": True})
        self.assertEqual(change.new_thresholds, {"new": True})
        self.assertEqual(audit.details["old_weight"], "0.450")
        self.assertEqual(audit.details["new_weight"], "0.600")
        self.assertFalse(audit.details["old_is_active"])
        self.assertTrue(audit.details["new_is_active"])

    def test_demo_runs_provisional_overrides_only_for_synthetic_customers(self) -> None:
        class FakeDetectionService:
            def evaluate_detailed(self, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace(
                    run_id="demo-run",
                    created_alerts=2,
                    evaluation=DetectionEvaluation(
                        results=[
                            SimpleNamespace(
                                rule_code="R01",
                                customer_id=11,
                                result_status="evaluated",
                                parameter_status="PROVISIONAL",
                                score=Decimal("0.7500"),
                                transactions=[
                                    SimpleNamespace(transaction_no="D-R01-001")
                                ],
                            )
                        ],
                        summary={"rules": {"R01": {"elapsed_ms": 1.0}}},
                    ),
                )

        detection = FakeDetectionService()
        service = DemoService(SimpleNamespace(), detection)
        with patch(
            "backend.services.demo_service.seed_demo_data",
            return_value={
                "customers": 24,
                "accounts": 24,
                "transactions": 80,
                "rules": 15,
                "demo_customer_ids": list(range(11, 35)),
                "demo_suspicious_customer_ids": [22],
                "scenarios": [
                    {
                        "rule_code": "R01",
                        "customer_no": "DEMO-001",
                        "account_no": "DEMO-ACC-001",
                        "customer_id": 11,
                        "intent": "Near-limit activity.",
                        "expected_signal": "score >= 0.50",
                    }
                ],
            },
        ), patch.object(
            DemoService,
            "status",
            return_value={
                "seeded": True,
                "customer_rows": [],
                "account_rows": [],
                "transaction_rows": [],
                "scenarios": [],
            },
        ):
            result = service.seed(actor_id=7)

        expected_demo_ids = set(range(11, 35))
        self.assertEqual(detection.kwargs["customer_ids"], expected_demo_ids)
        self.assertEqual(
            detection.kwargs["transaction_customer_ids"], expected_demo_ids
        )
        self.assertEqual(detection.kwargs["suspicious_customer_ids"], {22})
        self.assertEqual(
            set(detection.kwargs["rule_overrides"]),
            {f"R{number:02d}" for number in range(1, 16)},
        )
        self.assertTrue(result["demo_only_parameters"])
        self.assertEqual(result["created_alerts"], 2)
        self.assertEqual(result["run_id"], "demo-run")
        self.assertTrue(result["demo_data_isolated"])
        self.assertTrue(result["scenarios"][0]["observed_signal"])
        self.assertTrue(result["scenarios"][0]["passed"])
        self.assertEqual(
            result["scenarios"][0]["evidence_transaction_numbers"], ["D-R01-001"]
        )

    def test_demo_can_evaluate_saved_active_rule_settings(self) -> None:
        class FakeDetectionService:
            def evaluate_detailed(self, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace(
                    run_id="saved-run",
                    created_alerts=0,
                    evaluation=DetectionEvaluation(results=[], summary={"rules": {}}),
                )

        scenario = {
            "rule_code": "R01",
            "customer_no": "DEMO-001",
            "account_no": "DEMO-ACC-001",
            "customer_id": 11,
            "intent": "Near-limit activity.",
            "expected_signal": "score >= 0.50",
        }
        detection = FakeDetectionService()
        service = DemoService(SimpleNamespace(), detection)
        with patch(
            "backend.services.demo_service.seed_demo_data",
            return_value={
                "customers": 24,
                "accounts": 24,
                "transactions": 80,
                "rules": 15,
                "demo_customer_ids": [11],
                "demo_suspicious_customer_ids": [22],
                "scenarios": [scenario],
            },
        ), patch.object(
            DemoService,
            "status",
            return_value={
                "seeded": True,
                "customer_rows": [],
                "account_rows": [],
                "transaction_rows": [],
                "scenarios": [],
            },
        ):
            result = service.seed(actor_id=7, use_saved_rules=True)

        self.assertIsNone(detection.kwargs["rule_overrides"])
        self.assertTrue(result["saved_rule_settings_used"])
        self.assertFalse(result["demo_only_parameters"])
        self.assertEqual(result["parameter_mode"], "saved_active_rules")
        self.assertEqual(result["scenarios"][0]["result_status"], "not_evaluated_inactive")
        self.assertIsNone(result["scenarios"][0]["passed"])

    def test_demo_status_exposes_fixture_inventory_and_rule_targets(self) -> None:
        class ScalarRows(list):
            def unique(self):
                return self

        customers = []
        accounts = []
        for index in range(1, 25):
            customer = SimpleNamespace(
                customer_id=index,
                customer_no=f"DEMO-{index:03d}",
                full_name=f"Demo Customer {index:02d}",
                customer_type="BIREYSEL" if index <= 3 else "KURUMSAL",
                monthly_income=Decimal("50000"),
                is_active=True,
                accounts=[],
            )
            account = SimpleNamespace(
                account_id=index,
                account_no=f"DEMO-ACC-{index:03d}",
                customer_id=index,
                customer=customer,
                currency="TRY",
                account_type="current",
                opened_at=None,
                is_active=True,
            )
            customer.accounts.append(account)
            customers.append(customer)
            accounts.append(account)

        transaction = SimpleNamespace(
            transaction_no="D-R01-001",
            sender_account_id=1,
            receiver_account_id=2,
            sender_account=accounts[0],
            receiver_account=accounts[1],
            amount=Decimal("9500"),
            currency="TRY",
            tx_time=datetime(2026, 1, 1, 12),
            channel="internet",
            is_active=True,
        )

        class FakeSession:
            def __init__(self):
                self.query_count = 0

            def scalars(self, _statement):
                self.query_count += 1
                return ScalarRows(customers if self.query_count == 1 else [transaction])

        inventory = DemoService(FakeSession(), SimpleNamespace()).status()

        self.assertTrue(inventory["seeded"])
        self.assertTrue(inventory["fixture_ready"])
        self.assertEqual(inventory["customers"], 24)
        self.assertEqual(inventory["accounts"], 24)
        self.assertEqual(inventory["transactions"], 1)
        self.assertEqual(len(inventory["customer_rows"]), 24)
        self.assertEqual(inventory["transaction_rows"][0]["transaction_no"], "D-R01-001")
        self.assertEqual(len(inventory["scenarios"]), 15)
        self.assertEqual(inventory["scenarios"][0]["customer_no"], "DEMO-001")

    def test_deduplication_key_is_stable_and_scoped(self) -> None:
        transactions = [
            SimpleNamespace(transaction_id=7),
            SimpleNamespace(transaction_id=3),
        ]
        key = _dedup("R02", transactions, scope_id=12)
        self.assertEqual(key, _dedup("R02", transactions[::-1], scope_id=12))
        self.assertNotEqual(key, _dedup("R02", transactions, scope_id=13))

    def test_database_urls_use_the_installed_postgres_driver(self) -> None:
        self.assertEqual(
            normalize_database_url("postgresql://user:pass@localhost/db"),
            "postgresql+psycopg2://user:pass@localhost/db",
        )
        self.assertEqual(
            normalize_database_url("postgresql+psycopg://user:pass@localhost/db"),
            "postgresql+psycopg2://user:pass@localhost/db",
        )


if __name__ == "__main__":
    unittest.main()
