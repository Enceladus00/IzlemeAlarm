"""R16, S1, S2, R17, R18 (API design 7.12) without a database."""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.detection.engine import DetectionEngine
from backend.detection.registry import load_rule_registry
from backend.detection.rules.r18_combined_score import combined_score
from backend.services.rule_service import InvalidRuleThresholds, validate_thresholds

AS_OF = datetime(2026, 11, 4, 12, 0)


def provisional(values):
    return {
        "BIREYSEL": {"status": "PROVISIONAL", "values": values},
        "KURUMSAL": {"status": "UNSET", "values": {}},
    }


VALID = {
    "R16": {"countries": ["IR", "KP"], "limits": {"TRY": "20000"}, "window_days": 30, "x_esik": "0", "x_kesin": "1.609"},
    "S1": {"limits": {"TRY": "10000"}, "round_unit": "1000", "min_count": 5, "x_esik": "0.6", "x_kesin": "0.9"},
    "S2": {"window_days": 30, "mad_floor": "0.2", "cash_accounts": [], "x_esik": "4", "x_kesin": "6"},
    "R17": {"window_days": 30, "min_rules": 2, "excluded_rules": ["R02", "R17", "R18"], "open_statuses": ["new", "in_review"]},
    "R18": {"p": "4", "alert_threshold": "0.5"},
}


@pytest.mark.parametrize("code", sorted(VALID))
def test_valid_parameters_are_accepted(code):
    normalized = validate_thresholds(code, provisional(VALID[code]))
    assert normalized["BIREYSEL"]["status"] == "PROVISIONAL"


@pytest.mark.parametrize(
    ("code", "patch"),
    [
        ("R17", {"open_statuses": ["OPEN"]}),
        ("R17", {"open_statuses": []}),
        ("R17", {"excluded_rules": ["R99"]}),
        ("R17", {"min_rules": 1}),
        ("R16", {"countries": ["ir"]}),
        ("R16", {"countries": []}),
        ("R16", {"countries": ["IR", "IR"]}),
        ("R16", {"x_esik": "2", "x_kesin": "1"}),
        ("S1", {"x_esik": "0.9", "x_kesin": "0.9"}),
        ("S1", {"x_kesin": "1.5"}),
        ("S1", {"round_unit": "0"}),
        ("S1", {"min_count": 0}),
        ("S2", {"x_esik": "6", "x_kesin": "4"}),
        ("S2", {"mad_floor": "0"}),
        ("R18", {"p": "0.5"}),
        ("R18", {"alert_threshold": "0"}),
        ("R18", {"alert_threshold": "1.2"}),
    ],
)
def test_invalid_parameters_are_rejected(code, patch):
    with pytest.raises(InvalidRuleThresholds):
        validate_thresholds(code, provisional({**VALID[code], **patch}))


def test_combined_score_is_capped_at_one():
    # Two rules with weight 1 and score 0.9: (2 * 0.9^4)^(1/4) ~ 1.07 -> 1.
    assert combined_score([Decimal("0.9"), Decimal("0.9")], Decimal("4")) == Decimal("1.0000")
    assert combined_score([Decimal("0.3"), Decimal("0.4")], Decimal("1")) == Decimal("0.7000")
    assert combined_score([], Decimal("4")) == Decimal("0.0000")


# --- engine-level checks with in-memory objects -------------------------------


def account(account_id, customer):
    return SimpleNamespace(account_id=account_id, customer_id=customer.customer_id, customer=customer, is_active=True)


def customer(customer_id, customer_type="BIREYSEL"):
    c = SimpleNamespace(customer_id=customer_id, customer_type=customer_type, accounts=[], monthly_income=Decimal("10000"))
    return c


def tx(tx_id, sender, receiver, amount, *, days_ago=1, country="TR", currency="TRY"):
    return SimpleNamespace(
        transaction_id=tx_id,
        sender_account_id=sender.account_id,
        receiver_account_id=receiver.account_id,
        sender_account=sender,
        receiver_account=receiver,
        amount=Decimal(amount),
        currency=currency,
        tx_time=AS_OF - timedelta(days=days_ago),
        country_code=country,
        channel="internet",
    )


def rules(active: dict[str, dict]):
    rows = {}
    for code in load_rule_registry():
        thresholds = provisional(active[code]) if code in active else {}
        rows[code] = SimpleNamespace(rule_code=code, rule_id=len(rows) + 1, is_active=code in active, thresholds=thresholds, weight=Decimal("1.000"))
    return rows


def _setup():
    me = customer(1)
    other = customer(2)
    mine = account(10, me)
    theirs = account(20, other)
    me.accounts = [mine]
    other.accounts = [theirs]
    return me, other, mine, theirs


def test_r16_scores_listed_country_volume_by_ln_ratio():
    me, other, mine, theirs = _setup()
    transactions = [tx(1, mine, theirs, "100000", country="IR"), tx(2, mine, theirs, "5000", country="TR")]
    evaluation = DetectionEngine().evaluate([me, other], transactions, rules({"R16": VALID["R16"]}), as_of=AS_OF)
    result = next(r for r in evaluation.results if r.rule_code == "R16" and r.customer_id == 1)
    assert result.raw_x == (Decimal("100000") / Decimal("20000")).ln()
    assert Decimal("0.9") <= result.score < Decimal("0.91")  # x = ln 5 ~ x_kesin (1.609)
    assert [t.transaction_id for t in result.transactions] == [1]


def test_s1_is_signal_only_and_measures_round_share():
    me, other, mine, theirs = _setup()
    transactions = [tx(i, mine, theirs, "20000" if i % 2 else "20500") for i in range(1, 7)]
    evaluation = DetectionEngine().evaluate([me, other], transactions, rules({"S1": VALID["S1"]}), as_of=AS_OF)
    result = next(r for r in evaluation.results if r.rule_code == "S1" and r.customer_id == 1)
    assert result.alert_mode == "SIGNAL_ONLY"
    assert result.raw_x == Decimal("0.5")  # 3 of 6 big transfers are round thousands


def test_r18_combines_the_runs_scores_and_runs_after_signals():
    me, other, mine, theirs = _setup()
    transactions = [tx(1, mine, theirs, "100000", country="IR")]
    active = {"R16": VALID["R16"], "R18": {"p": "4", "alert_threshold": "0.5"}}
    evaluation = DetectionEngine().evaluate([me, other], transactions, rules(active), as_of=AS_OF)
    combined = next(r for r in evaluation.results if r.rule_code == "R18" and r.customer_id == 1)
    r16 = next(r for r in evaluation.results if r.rule_code == "R16" and r.customer_id == 1)
    assert combined.score == r16.score  # one contributor with weight 1: A = u
    assert combined.alert_threshold == Decimal("0.5")
    last = combined.step_trace[-2]["details"]
    assert last["A"] == str(r16.score) and last["top_rules"].startswith("R16")
    contributions = combined.step_trace[1]["details"]["contributions"]
    assert [c["rule_code"] for c in contributions] == ["R16"]


def test_r17_is_deferred_to_persistence():
    me, other, _mine, _theirs = _setup()
    evaluation = DetectionEngine().evaluate([me, other], [], rules({"R17": VALID["R17"]}), as_of=AS_OF)
    deferred = [r for r in evaluation.results if r.rule_code == "R17" and r.customer_type == "BIREYSEL"]
    assert deferred and all(r.score is None and r.alert_mode == "SEVERITY_RAISE" for r in deferred)
