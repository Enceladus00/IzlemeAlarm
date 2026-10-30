from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from backend.demo import DEMO_RULE_OVERRIDES, DEMO_SCENARIOS, seed_demo_data
from backend.models import Account, Customer, Transaction
from backend.services.detection_service import DetectionService


class DemoService:
    def __init__(self, session: Session, detection_service: DetectionService) -> None:
        self._session = session
        self._detection_service = detection_service

    def status(self) -> dict[str, Any]:
        customers = list(
            self._session.scalars(
                select(Customer)
                .where(Customer.customer_no.like("DEMO-%"))
                .options(selectinload(Customer.accounts))
                .order_by(Customer.customer_no)
            )
        )
        customer_ids = {customer.customer_id for customer in customers}
        accounts = sorted(
            (account for customer in customers for account in customer.accounts),
            key=lambda account: account.account_no,
        )
        sender = aliased(Account)
        receiver = aliased(Account)
        transactions = (
            list(
                self._session.scalars(
                    select(Transaction)
                    .join(
                        sender,
                        Transaction.sender_account_id == sender.account_id,
                    )
                    .join(
                        receiver,
                        Transaction.receiver_account_id == receiver.account_id,
                    )
                    .where(
                        sender.customer_id.in_(customer_ids),
                        receiver.customer_id.in_(customer_ids),
                        Transaction.transaction_no.like("D-R%"),
                    )
                    .options(
                        joinedload(Transaction.sender_account),
                        joinedload(Transaction.receiver_account),
                    )
                    .order_by(Transaction.tx_time, Transaction.transaction_no)
                ).unique()
            )
            if customer_ids
            else []
        )
        customers_by_number = {
            customer.customer_no: customer for customer in customers
        }
        account_customer_numbers = {
            account.account_id: customer.customer_no
            for customer in customers
            for account in customer.accounts
        }
        scenarios = [
            {
                "rule_code": rule_code,
                "customer_no": customer_no,
                "account_no": account_no,
                "customer_id": customers_by_number[customer_no].customer_id,
                "intent": intent,
                "expected_signal": "score >= 0.50",
            }
            for rule_code, customer_no, account_no, intent in DEMO_SCENARIOS
            if customer_no in customers_by_number
        ]
        return {
            "seeded": bool(customers),
            "fixture_ready": all(
                f"DEMO-{index:03d}" in customers_by_number
                for index in range(1, 25)
            ),
            "customers": len(customers),
            "accounts": len(accounts),
            "transactions": len(transactions),
            "customer_rows": [
                {
                    "customer_no": customer.customer_no,
                    "full_name": customer.full_name,
                    "customer_type": customer.customer_type,
                    "monthly_income": (
                        str(customer.monthly_income)
                        if customer.monthly_income is not None
                        else None
                    ),
                    "account_count": len(customer.accounts),
                    "is_active": customer.is_active,
                }
                for customer in customers
            ],
            "account_rows": [
                {
                    "account_no": account.account_no,
                    "customer_no": account_customer_numbers[account.account_id],
                    "currency": account.currency,
                    "account_type": account.account_type,
                    "opened_at": (
                        account.opened_at.isoformat()
                        if account.opened_at is not None
                        else None
                    ),
                    "is_active": account.is_active,
                }
                for account in accounts
            ],
            "transaction_rows": [
                {
                    "transaction_no": transaction.transaction_no,
                    "sender_customer_no": account_customer_numbers[
                        transaction.sender_account_id
                    ],
                    "sender_account_no": transaction.sender_account.account_no,
                    "receiver_customer_no": account_customer_numbers[
                        transaction.receiver_account_id
                    ],
                    "receiver_account_no": transaction.receiver_account.account_no,
                    "amount": str(transaction.amount),
                    "currency": transaction.currency,
                    "tx_time": transaction.tx_time.isoformat(),
                    "channel": transaction.channel,
                    "is_active": transaction.is_active,
                }
                for transaction in transactions
            ],
            "scenarios": scenarios,
        }

    def seed(
        self, actor_id: int, *, use_saved_rules: bool = False
    ) -> dict[str, Any]:
        try:
            as_of = datetime.now()
            counts = seed_demo_data(self._session, as_of=as_of)
            outcome = self._detection_service.evaluate_detailed(
                actor_id=actor_id,
                automatic=True,
                as_of=as_of,
                customer_ids=set(counts["demo_customer_ids"]),
                transaction_customer_ids=set(counts["demo_customer_ids"]),
                suspicious_customer_ids=set(
                    counts["demo_suspicious_customer_ids"]
                ),
                rule_overrides=None if use_saved_rules else DEMO_RULE_OVERRIDES,
            )
        except SQLAlchemyError:
            self._session.rollback()
            raise
        results_by_target = {
            (result.rule_code, result.customer_id): result
            for result in outcome.evaluation.results
        }
        scenarios = []
        for scenario in counts["scenarios"]:
            result = results_by_target.get(
                (scenario["rule_code"], scenario["customer_id"])
            )
            score = result.score if result else None
            triggered = (
                result is not None
                and result.result_status == "evaluated"
                and score is not None
                and score >= 0.5
            )
            scenarios.append(
                {
                    **scenario,
                    "result_status": (
                        result.result_status if result else "not_evaluated_inactive"
                    ),
                    "parameter_status": (
                        result.parameter_status if result else None
                    ),
                    "score": str(score) if score is not None else None,
                    "evidence_transactions": (
                        len(result.transactions) if result else 0
                    ),
                    "evidence_transaction_numbers": [
                        transaction.transaction_no
                        for transaction in (result.transactions if result else [])
                    ],
                    "observed_signal": triggered if result else None,
                    "passed": triggered if result else None,
                }
            )
        return {
            **self.status(),
            **counts,
            "run_id": str(outcome.run_id),
            "created_alerts": outcome.created_alerts,
            "demo_only_parameters": not use_saved_rules,
            "parameter_mode": (
                "saved_active_rules" if use_saved_rules else "demo_provisional"
            ),
            "saved_rule_settings_used": use_saved_rules,
            "demo_data_isolated": True,
            "synthetic_suspicious_customer_no": "DEMO-022",
            "rule_summary": outcome.evaluation.summary["rules"],
            "scenarios": scenarios,
        }
