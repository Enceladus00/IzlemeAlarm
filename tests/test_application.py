import unittest
from types import SimpleNamespace

from sqlalchemy.orm import configure_mappers

from backend.db_url import normalize_database_url
from backend.main import app
from backend.models import AlertStatusHistory, AuditLog, Base
from backend.repositories.alert_repository import SqlAlchemyAlertRepository
from backend.repositories.transaction_repository import (
    SqlAlchemyTransactionRepository,
    TransactionFilters,
)
from backend.rules import _dedup
from backend.services.alert_service import AlertService
from backend.services.rule_service import (
    InvalidRuleThresholds,
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
            scalar=lambda _statement: SimpleNamespace(user_id=7),
            add=records.append,
            commit=lambda: None,
        )

        result = AlertService(SqlAlchemyAlertRepository(session)).update_status(
            12,
            "in_review",
            "Reviewed account activity.",
        )

        history = next(record for record in records if isinstance(record, AlertStatusHistory))
        audit = next(record for record in records if isinstance(record, AuditLog))
        self.assertEqual(result, {"alert_id": 12, "status": "in_review", "changed": False})
        self.assertEqual(history.old_status, "in_review")
        self.assertEqual(history.new_status, "in_review")
        self.assertEqual(history.note, "Reviewed account activity.")
        self.assertEqual(audit.action, "alert.note_added")

    def test_entity_relationships_configure(self) -> None:
        configure_mappers()
        self.assertIn("customer", Base.metadata.tables)
        self.assertIn("transaction", Base.metadata.tables)
        self.assertIn("alert_status_history", Base.metadata.tables)

    def test_demo_rule_thresholds_are_valid(self) -> None:
        self.assertEqual(
            validate_thresholds(
                "R1",
                {
                    "amount_limit": 10000,
                    "proximity_percent": 10,
                    "transaction_count": 2,
                    "window_minutes": 60,
                },
            )["amount_limit"],
            10000,
        )
        self.assertEqual(
            validate_thresholds(
                "R4", {"countries": ["TR", "IL"], "enabled": True}
            )["countries"],
            ["TR", "IL"],
        )

    def test_rule_thresholds_reject_unsafe_or_ambiguous_values(self) -> None:
        invalid = [
            ("R1", {"amount_limit": float("inf"), "proximity_percent": 10,
                    "transaction_count": 2, "window_minutes": 60}),
            ("R2", {"outflow_ratio": 1.1, "window_minutes": 60}),
            ("R3", {"average_multiplier": 3, "minimum_history_count": 5.5}),
            ("R4", {"countries": ["Turkey"], "enabled": True}),
            ("R1", {"amount_limit": 10000}),
        ]
        for rule_code, thresholds in invalid:
            with self.subTest(rule_code=rule_code, thresholds=thresholds):
                with self.assertRaises(InvalidRuleThresholds):
                    validate_thresholds(rule_code, thresholds)

    def test_deduplication_key_is_stable_and_scoped(self) -> None:
        transactions = [
            SimpleNamespace(transaction_id=7),
            SimpleNamespace(transaction_id=3),
        ]
        key = _dedup("R2", transactions, scope_id=12)
        self.assertEqual(key, _dedup("R2", transactions[::-1], scope_id=12))
        self.assertNotEqual(key, _dedup("R2", transactions, scope_id=13))

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
