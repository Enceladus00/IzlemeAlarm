import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from types import SimpleNamespace

from sqlalchemy.orm import configure_mappers

from backend.db_url import normalize_database_url
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

    def test_rule_activation_rejects_unset_parameters(self) -> None:
        class FakeRuleRepository:
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

        with self.assertRaises(InvalidRuleThresholds):
            RuleService(FakeRuleRepository()).update_rule(
                "R02",
                {
                    "BIREYSEL": {"status": "UNSET", "values": {}},
                    "KURUMSAL": {"status": "UNSET", "values": {}},
                },
                True,
                actor_id=7,
            )

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
            def evaluate(self, **kwargs):
                self.kwargs = kwargs
                return 2

        detection = FakeDetectionService()
        service = DemoService(SimpleNamespace(), detection)
        with patch(
            "backend.services.demo_service.seed_demo_data",
            return_value={
                "customers": 10,
                "accounts": 10,
                "transactions": 6,
                "rules": 3,
                "demo_customer_ids": [11, 12, 13],
            },
        ):
            result = service.seed(actor_id=7)

        self.assertEqual(detection.kwargs["customer_ids"], {11, 12, 13})
        self.assertEqual(set(detection.kwargs["rule_overrides"]), {"R01", "R02", "R03"})
        self.assertTrue(result["demo_only_parameters"])
        self.assertEqual(result["created_alerts"], 2)

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
