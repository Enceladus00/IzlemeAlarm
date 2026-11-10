"""Rule changes from the threshold review (Analiz Formu v0.11, 7.18).

Each test is one acceptance check of the review, using the decided values.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.detection.metadata import RuleResultEvidence
from backend.detection.parameters import validate_rule_parameters
from backend.detection.registry import load_rule_registry
from backend.detection.rules.r02_large_single import LargeSingleTransactionRule
from backend.detection.rules.r03_cash_deposits import CashDepositsRule
from backend.detection.rules.r04_income_volume import IncomeVolumeRule
from backend.detection.rules.r05_unusual_amount import UnusualAmountRule
from backend.detection.rules.r06_velocity import VelocityIncreaseRule
from backend.detection.rules.r13_layering import LayeringChainRule
from backend.detection.rules.r14_cycles import CyclePingPongRule
from backend.detection.rules.r18_combined_score import SUPPRESSED_NOTE, CombinedScoreRule
from backend.detection.scoring import calculate_score

AS_OF = datetime(2026, 11, 9, 12)  # a Monday


def customer(customer_id, customer_type="BIREYSEL", income="50000"):
    return SimpleNamespace(
        customer_id=customer_id,
        customer_type=customer_type,
        monthly_income=Decimal(income) if income is not None else None,
        accounts=[],
    )


def tx(
    tx_id,
    amount,
    *,
    sender=1,
    receiver=2,
    sender_account=None,
    receiver_account=None,
    at=None,
    currency="TRY",
    channel="internet",
):
    return SimpleNamespace(
        transaction_id=tx_id,
        amount=Decimal(str(amount)),
        currency=currency,
        channel=channel,
        country_code="TR",
        tx_time=at or AS_OF - timedelta(hours=1),
        sender_account_id=sender_account or sender * 10,
        receiver_account_id=receiver_account or receiver * 10,
        sender_account=SimpleNamespace(customer_id=sender),
        receiver_account=SimpleNamespace(customer_id=receiver),
    )


def params(values, customer_type="BIREYSEL"):
    return {customer_type: {"status": "PROVISIONAL", "values": values}}


def score_of(raw):
    if raw.score_override is not None:
        return raw.score_override
    if raw.x_esik is None and raw.binary_limit is None:
        return Decimal("0")  # as the engine does
    return calculate_score(
        raw.raw_x,
        x_esik=raw.x_esik,
        x_kesin=raw.x_kesin,
        binary_limit=raw.binary_limit,
        force_zero=raw.force_zero,
    )


def normalized(code, values):
    """Run the values through the rule's parameter model, as the API does."""
    model = load_rule_registry()[code].definition.parameter_model
    thresholds = {
        "BIREYSEL": {"status": "PROVISIONAL", "values": values},
        "KURUMSAL": {"status": "UNSET", "values": {}},
    }
    return validate_rule_parameters(code, model, thresholds)["BIREYSEL"]["values"]


# --- R14: minimum amount -------------------------------------------------------

R14 = {
    "window_days": 30,
    "max_cycle_length": 5,
    "min_retained": "0.7",
    "pingpong_tolerance": "0.1",
    "cash_accounts": [],
    "x_esik": 3,
    "x_kesin": 6,
    "limits": {"TRY": "30000"},
}


def cycle(first, second, third):
    return [
        tx(1, first, sender=1, receiver=2, at=AS_OF - timedelta(hours=3)),
        tx(2, second, sender=2, receiver=3, at=AS_OF - timedelta(hours=2)),
        tx(3, third, sender=3, receiver=1, at=AS_OF - timedelta(hours=1)),
    ]


def run_r14(transactions, values=None):
    return CyclePingPongRule().evaluate_raw(
        [customer(1), customer(2), customer(3)],
        transactions,
        params(normalized("R14", values or R14)),
        as_of=AS_OF,
    )


def test_r14_small_cycle_opens_no_alert():
    results = run_r14(cycle(300, 300, 300))
    assert all(score_of(result) == 0 for result in results)
    assert all(result.transactions == [] for result in results)


def test_r14_large_cycle_opens_high_alert():
    results = run_r14(cycle(50000, 45000, 40000))  # 80% comes back
    assert all(score_of(result) >= Decimal("0.9") for result in results)
    assert all(len(result.transactions) == 3 for result in results)


def test_r14_small_pingpong_opens_no_alert():
    transactions = []
    for index in range(3):  # 5.000 TL there and back, three times in the month
        day = AS_OF - timedelta(days=3 * index + 2)
        transactions.append(tx(10 + 2 * index, 5000, sender=1, receiver=2, at=day))
        transactions.append(
            tx(11 + 2 * index, 5000, sender=2, receiver=1, at=day + timedelta(hours=5))
        )
    results = run_r14(transactions)
    assert all(score_of(result) == 0 for result in results)

    # The same pattern at 40.000 TL is at least three pairs: alert (x_esik = 3).
    big = [
        SimpleNamespace(**{**vars(item), "amount": Decimal("40000")})
        for item in transactions
    ]
    assert all(score_of(result) >= Decimal("0.5") for result in run_r14(big)[:2])


def test_r14_without_minimum_keeps_the_old_behaviour():
    values = {key: value for key, value in R14.items() if key != "limits"}
    assert "limits" not in normalized("R14", values)
    results = run_r14(cycle(300, 300, 300), values)
    assert all(score_of(result) == Decimal("1") for result in results)


def test_minimum_amount_is_validated_like_other_limits():
    with pytest.raises(ValueError):
        normalized("R14", {**R14, "limits": {"try": "30000"}})
    with pytest.raises(ValueError):
        normalized("R14", {**R14, "limits": {"TRY": "0"}})
    with pytest.raises(ValueError):
        normalized("R14", {**R14, "limits": {}})


# --- R18: skip when a single rule already alerts -------------------------------


def prior(rule_code, score, alert_mode="ALERT", customer_id=1):
    return RuleResultEvidence(
        rule_code=rule_code,
        customer_id=customer_id,
        customer_type="BIREYSEL",
        parameter_snapshot={},
        parameter_status="PROVISIONAL",
        result_status="evaluated",
        raw_x=Decimal("0"),
        score=Decimal(score),
        step_trace=[],
        transactions=[],
        alert_mode=alert_mode,
    )


def run_r18(prior_results):
    codes = {result.rule_code for result in prior_results}
    return CombinedScoreRule().evaluate_combined(
        [customer(1)],
        params({"p": "4", "alert_threshold": "0.55"}),
        prior_results,
        {code: Decimal("1") for code in codes},
        as_of=AS_OF,
    )[0]


def test_r18_is_skipped_when_a_single_rule_already_alerts():
    result = run_r18([prior("R05", "0.9")])
    assert result.score_override == Decimal("0")
    assert result.raw_x == Decimal("0.9000")  # A stays visible
    last = result.step_trace[-1]
    assert last["status"] == "blocked"
    assert last["details"]["note"] == SUPPRESSED_NOTE
    assert last["details"]["single_rule_alerts"] == "R05"


def test_r18_alerts_on_three_rules_below_the_single_rule_threshold():
    result = run_r18([prior("R05", "0.45"), prior("R06", "0.45"), prior("R10", "0.45")])
    assert result.score_override == Decimal("0.5922")  # 0.45 * 3^(1/4)
    assert result.score_override >= Decimal("0.55")
    assert result.step_trace[-1]["status"] == "completed"


def test_r18_does_not_alert_on_two_rules_below_the_threshold():
    result = run_r18([prior("R05", "0.45"), prior("R10", "0.45")])
    assert result.score_override == Decimal("0.5351")  # 0.45 * 2^(1/4) < 0.55
    assert "note" not in result.step_trace[-1]["details"]


def test_r18_signal_rules_do_not_block_the_combined_alert():
    result = run_r18(
        [
            prior("R05", "0.45"),
            prior("R10", "0.45"),
            prior("S1", "0.8", alert_mode="SIGNAL_ONLY"),
            prior("S2", "0.7", alert_mode="SIGNAL_ONLY"),
        ]
    )
    assert result.score_override >= Decimal("0.55")
    assert result.step_trace[-1]["status"] == "completed"


# --- R02: transfers between the customer's own accounts ------------------------


def run_r02(transaction, customer_id=1):
    return LargeSingleTransactionRule().evaluate_raw(
        [customer(customer_id)],
        [transaction],
        params({"limits": {"TRY": "370000"}}),
        as_of=AS_OF,
    )[0]


def test_r02_ignores_transfers_between_own_accounts():
    own = tx(1, 500000, sender=1, receiver=1, sender_account=11, receiver_account=12)
    result = run_r02(own)
    assert score_of(result) == 0
    assert result.transactions == []


def test_r02_still_alerts_on_outgoing_and_incoming_transfers():
    assert score_of(run_r02(tx(1, 500000, sender=1, receiver=2))) == Decimal("1.0000")
    incoming = run_r02(tx(2, 400000, sender=2, receiver=1))
    assert score_of(incoming) == Decimal("1.0000")
    assert [item.transaction_id for item in incoming.transactions] == [2]


# --- R03: counted per customer, not per account --------------------------------

R03 = {
    "limits": {"TRY": "370000"},
    "cash_channels": ["atm", "branch"],
    "window_days": 7,
    "x_esik": 5,
    "x_kesin": 10,
}


def deposits(per_account):
    """Cash deposits into customer 1's accounts: {account_id: count}."""
    items = []
    for account_id, count in per_account.items():
        for index in range(count):
            items.append(
                tx(
                    len(items) + 1,
                    20000,
                    sender=9,
                    receiver=1,
                    receiver_account=account_id,
                    channel="atm",
                    at=AS_OF - timedelta(days=index + 1),
                )
            )
    return items


def run_r03(per_account):
    return CashDepositsRule().evaluate_raw(
        [customer(1)], deposits(per_account), params(R03), as_of=AS_OF
    )[0]


def test_r03_counts_deposits_across_the_customers_accounts():
    result = run_r03({11: 2, 12: 2, 13: 2})
    assert result.raw_x == Decimal("6")
    assert score_of(result) >= Decimal("0.5")
    assert len(result.transactions) == 6
    assert result.step_trace[1]["details"]["account_ids"] == [11, 12, 13]


def test_r03_four_deposits_into_one_account_open_no_alert():
    result = run_r03({11: 4})
    assert result.raw_x == Decimal("4")
    assert score_of(result) < Decimal("0.5")


# --- R04: minimum monthly volume -----------------------------------------------

R04 = {"window_days": 30, "x_esik": "3", "x_kesin": "6", "limits": {"TRY": "100000"}}


def run_r04(income, incoming):
    return IncomeVolumeRule().evaluate_raw(
        [customer(1, income=income)],
        [tx(1, incoming, sender=2, receiver=1, at=AS_OF - timedelta(days=3))],
        params(normalized("R04", R04)),
        as_of=AS_OF,
    )[0]


def test_r04_low_volume_student_opens_no_alert():
    result = run_r04("4500", 15000)  # 3.3 times the income, but only 15.000 TL
    assert result.force_zero
    assert score_of(result) == 0
    check = result.step_trace[3]
    assert check["status"] == "blocked"
    assert check["details"]["minimum_volume_met"] is False


def test_r04_six_times_income_above_the_minimum_is_a_high_alert():
    result = run_r04("20000", 120000)
    assert result.raw_x == Decimal("6")
    assert score_of(result) >= Decimal("0.9")
    assert result.step_trace[3]["details"]["minimum_volume_met"] is True


# --- R05: minimum transaction amount -------------------------------------------

R05 = {
    "history_days": 90,
    "kappa": "10",
    "mad_floor": "0.2",
    "income_bands": 5,
    "x_esik": "4",
    "x_kesin": "6",
    "limits": {"TRY": "30000"},
}


def run_r05(amount, values=None, currency="TRY"):
    history = [
        tx(index, 5000, sender=1, receiver=2, at=AS_OF - timedelta(days=index + 1))
        for index in range(1, 21)
    ]
    today = tx(100, amount, sender=1, receiver=2, currency=currency)
    return UnusualAmountRule().evaluate_raw(
        [customer(1)],
        [*history, today],
        params(normalized("R05", values or R05)),
        as_of=AS_OF,
    )[0]


def test_r05_ordinary_amount_below_the_minimum_opens_no_alert():
    result = run_r05(17000)
    assert score_of(result) == 0
    assert result.step_trace[0]["details"]["below_minimum_transaction_count"] == 1

    # It did alert before the minimum existed.
    without = {key: value for key, value in R05.items() if key != "limits"}
    assert score_of(run_r05(17000, without)) >= Decimal("0.5")


def test_r05_unusual_amount_above_the_minimum_alerts():
    result = run_r05(40000)
    assert score_of(result) >= Decimal("0.5")
    assert [item.transaction_id for item in result.transactions] == [100]


def test_r05_currency_without_a_minimum_is_not_evaluated():
    result = run_r05(40000, currency="USD")
    assert score_of(result) == 0
    assert result.ignored_currency_count == 1


# --- R06: last 7 days and the dispersion floor ---------------------------------


def r06_values(customer_type):
    values = {
        "history_weeks": 12,
        "season_factor": {},
        "x_esik": "3",
        "x_kesin": "5",
        "min_count": 5 if customer_type == "BIREYSEL" else 20,
    }
    if customer_type == "KURUMSAL":
        values["dispersion_k"] = "16"
    return values


def run_r06(weekly_history, current_count, customer_type="BIREYSEL"):
    """weekly_history: counts of the 7-day slices before the last 7 days."""
    window_start = datetime.combine(AS_OF.date() - timedelta(days=6), datetime.min.time())
    transactions = []
    for week_index, count in enumerate(weekly_history, 1):
        slice_start = window_start - timedelta(days=7 * week_index)
        for index in range(count):
            transactions.append(
                tx(
                    len(transactions) + 1,
                    100,
                    at=slice_start + timedelta(days=index % 7, minutes=index),
                )
            )
    for index in range(current_count):
        # Spread over the previous calendar week: invisible to a Monday-based week.
        transactions.append(
            tx(
                len(transactions) + 1,
                100,
                at=window_start + timedelta(days=index % 6, minutes=index),
            )
        )
    model = load_rule_registry()["R06"].definition.parameter_model
    values = model.model_validate(r06_values(customer_type)).model_dump(
        mode="json", exclude_none=True
    )
    return VelocityIncreaseRule().evaluate_raw(
        [customer(1, customer_type)],
        transactions,
        params(values, customer_type),
        as_of=AS_OF,
    )[0]


def test_r06_sees_the_last_seven_days_on_a_monday():
    assert AS_OF.weekday() == 0
    result = run_r06([3, 4] * 6, 15)  # usual: 3.5 a week
    assert result.step_trace[0]["details"]["current_week_count"] == 15
    assert result.step_trace[0]["details"]["history_weekly_counts"] == [4, 3] * 6
    assert score_of(result) >= Decimal("0.5")
    assert result.step_trace[1]["details"]["variance_floor_applied"] is False


def test_r06_dispersion_floor_tolerates_ordinary_swings_of_a_large_company():
    quiet = run_r06([41] * 12, 70, "KURUMSAL")
    assert score_of(quiet) < Decimal("0.5")
    details = quiet.step_trace[1]["details"]
    assert details["variance_floor_applied"] is True
    assert details["variance"] == pytest.approx(41 + 41 * 41 / 16)

    assert score_of(run_r06([41] * 12, 95, "KURUMSAL")) >= Decimal("0.5")


def test_r06_dispersion_floor_keeps_small_companies_sensitive():
    assert score_of(run_r06([2] * 12, 20, "KURUMSAL")) >= Decimal("0.5")


def test_r06_dispersion_k_must_be_positive():
    model = load_rule_registry()["R06"].definition.parameter_model
    with pytest.raises(ValueError):
        model.model_validate({**r06_values("KURUMSAL"), "dispersion_k": "0"})


# --- R13: minimum amount of the first transaction ------------------------------

R13 = {
    "window_days": 7,
    "max_step_hours": 24,
    "decay_low": "0.9",
    "decay_high": "0.99",
    "max_depth": 6,
    "cash_accounts": [],
    "x_esik": 3,
    "x_kesin": 5,
    "limits": {"TRY": "30000"},
}


def run_r13(amounts):
    transactions = [
        tx(
            index + 1,
            amount,
            sender=index + 1,
            receiver=index + 2,
            at=AS_OF - timedelta(hours=10 - index),
        )
        for index, amount in enumerate(amounts)
    ]
    return LayeringChainRule().evaluate_raw(
        [customer(index) for index in range(1, len(amounts) + 2)],
        transactions,
        params(normalized("R13", R13)),
        as_of=AS_OF,
    )


def test_r13_small_chain_opens_no_alert():
    results = run_r13([25000, 24000, 23000])
    assert all(score_of(result) == 0 for result in results)
    assert results[0].step_trace[1]["details"]["chain_start_transaction_count"] == 0


def test_r13_large_chain_alerts():
    results = run_r13([100000, 95000, 92000])
    assert all(result.raw_x == Decimal("3") for result in results)
    assert all(score_of(result) >= Decimal("0.5") for result in results)
