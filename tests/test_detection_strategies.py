import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from backend.detection.rules.r1_threshold import NearThresholdStrategy
from backend.detection.rules.r2_in_out import RapidOutflowStrategy
from backend.detection.rules.r3_anomaly import UnusualAmountStrategy
from backend.detection.rules.r4_country import RiskyCountryStrategy


def make_transaction(
    transaction_id: int,
    amount: str,
    minute: int,
    *,
    sender_id: int = 1,
    receiver_id: int = 2,
    currency: str = "TRY",
    country: str = "TR",
) -> SimpleNamespace:
    return SimpleNamespace(
        transaction_id=transaction_id,
        amount=Decimal(amount),
        tx_time=datetime(2026, 1, 1) + timedelta(minutes=minute),
        sender_account_id=sender_id,
        receiver_account_id=receiver_id,
        currency=currency,
        country_code=country,
        sender_account=SimpleNamespace(customer_id=10),
    )


class DetectionStrategyTests(unittest.TestCase):
    def test_near_threshold_strategy_is_independent(self) -> None:
        transactions = [
            make_transaction(1, "9500", 0),
            make_transaction(2, "9800", 20),
            make_transaction(3, "10000", 25),
        ]

        candidates = NearThresholdStrategy().detect(
            transactions,
            {
                "amount_limit": 10000,
                "proximity_percent": 10,
                "transaction_count": 2,
                "window_minutes": 60,
            },
            SimpleNamespace(),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            [transaction.transaction_id for transaction in candidates[0].transactions],
            [1, 2],
        )

    def test_rapid_outflow_strategy_uses_repository_accounts(self) -> None:
        account = SimpleNamespace(
            account_id=1,
            customer_id=10,
            currency="TRY",
        )
        transactions = [
            make_transaction(1, "100", 0, sender_id=2, receiver_id=1),
            make_transaction(2, "90", 20, sender_id=1, receiver_id=3),
        ]

        candidates = RapidOutflowStrategy().detect(
            transactions,
            {"outflow_ratio": 0.8, "window_minutes": 60},
            SimpleNamespace(list_accounts=lambda: [account]),
        )

        self.assertTrue(candidates)
        self.assertTrue(all(candidate.scope_id == account.account_id for candidate in candidates))

    def test_unusual_amount_strategy_uses_prior_customer_history(self) -> None:
        transactions = [
            make_transaction(index, "100", index)
            for index in range(1, 6)
        ] + [make_transaction(6, "400", 6)]

        candidates = UnusualAmountStrategy().detect(
            transactions,
            {"average_multiplier": 3, "minimum_history_count": 5},
            SimpleNamespace(),
        )

        self.assertEqual(
            [transaction.transaction_id for transaction in candidates[0].transactions],
            [6],
        )

    def test_risky_country_strategy_respects_enabled_flag(self) -> None:
        transactions = [
            make_transaction(1, "100", 0, country="IL"),
            make_transaction(2, "100", 1, country="US"),
        ]
        strategy = RiskyCountryStrategy()

        self.assertEqual(
            len(
                strategy.detect(
                    transactions,
                    {"enabled": False, "countries": ["IL"]},
                    SimpleNamespace(),
                )
            ),
            0,
        )
        self.assertEqual(
            len(
                strategy.detect(
                    transactions,
                    {"enabled": True, "countries": ["IL"]},
                    SimpleNamespace(),
                )
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
