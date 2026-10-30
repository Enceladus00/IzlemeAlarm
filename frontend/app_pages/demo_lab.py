import pandas as pd
import streamlit as st

from components.common import metric_row, page_header
from utils.api import ApiError, api_request, show_api_error


page_header(
    "Demo lab",
    "Browse the synthetic fixture, see which customer/account targets each rule, "
    "and compare scenario results with your saved thresholds.",
)

try:
    inventory = api_request("GET", "/demo/status")
except ApiError as error:
    show_api_error(error)
    st.stop()

st.session_state.setdefault("demo_last_run", None)
run_result = st.session_state.get("demo_last_run")

if not inventory["seed_enabled"]:
    st.warning(
        "Demo seeding is disabled. To enable it, set "
        "`ENABLE_DEMO_ENDPOINTS=true` in the API environment and restart the API."
    )
elif "upload:create" not in st.session_state.get("permissions", []):
    st.info("You can inspect the existing demo fixture, but your role cannot seed it.")
else:
    with st.container(border=True):
        st.subheader("Create or refresh the demo fixture")
        st.write(
            "This updates the reserved `DEMO-*` records and evaluates only demo "
            "customers and demo-to-demo transactions."
        )
        with st.form("demo-seed-form"):
            use_saved_rules = st.checkbox(
                "Use saved active rules and thresholds",
                value=False,
                help=(
                    "Turn this on to observe your configured thresholds. "
                    "Inactive rules will not run. Turn it off to run all rules "
                    "with synthetic provisional parameters."
                ),
            )
            submitted = st.form_submit_button(
                "Seed and evaluate demo",
                type="primary",
                icon=":material/science:",
            )
        if submitted:
            try:
                with st.spinner("Refreshing demo records and evaluating rules..."):
                    run_result = api_request(
                        "POST",
                        "/demo/seed",
                        params={"use_saved_rules": use_saved_rules},
                    )
                st.session_state["demo_last_run"] = run_result
                inventory = run_result
                st.success(
                    f"Demo ready: {run_result['customers']} customers, "
                    f"{run_result['accounts']} accounts, and "
                    f"{run_result['transactions']} transactions."
                )
            except ApiError as error:
                show_api_error(error)

if not inventory["seeded"]:
    st.info(
        "No demo fixture is currently stored. Once demo seeding is enabled, "
        "use the button above to create the customer, account, and transaction rows."
    )
    st.stop()
if not inventory["fixture_ready"]:
    st.warning(
        "A partial or older demo dataset is present. Refresh the fixture to add "
        "the full 24-customer, 15-rule scenario set."
    )

scenario_rows = (
    run_result["scenarios"] if run_result is not None else inventory["scenarios"]
)
rule_summary = run_result.get("rule_summary", {}) if run_result else {}

metric_row(
    [
        ("Demo customers", f"{inventory['customers']:,}"),
        ("Demo accounts", f"{inventory['accounts']:,}"),
        ("Demo transactions", f"{inventory['transactions']:,}"),
        ("Rules with scenarios", f"{len(inventory['scenarios']):,}"),
    ]
)

if run_result:
    st.caption(
        f"Latest run: `{run_result['run_id']}` · mode: "
        f"{run_result['parameter_mode']} · "
        f"{run_result['created_alerts']} new alerts."
    )
else:
    st.info(
        "Fixture records are visible below. Run the demo to see scores, evidence, "
        "and per-rule execution results."
    )

coverage_tab, customers_tab, accounts_tab, transactions_tab = st.tabs(
    ["Rule coverage", "Customers", "Accounts", "Transactions"]
)

with coverage_tab:
    coverage = pd.DataFrame(
        [
            {
                "Rule": scenario["rule_code"],
                "Designed customer": scenario["customer_no"],
                "Account": scenario["account_no"],
                "Scenario": scenario["intent"],
                "Expected signal": scenario["expected_signal"],
                "Result": scenario.get("result_status", "not run"),
                "Score": scenario.get("score"),
                "Evidence count": scenario.get("evidence_transactions", 0),
                "Evidence transaction IDs": ", ".join(
                    scenario.get("evidence_transaction_numbers", [])
                ),
                "Signal observed": scenario.get("observed_signal"),
                "Passed": scenario.get("passed"),
            }
            for scenario in scenario_rows
        ]
    )
    st.dataframe(
        coverage,
        hide_index=True,
        alt="Demo scenarios mapped to the customers and accounts designed to exercise each rule",
    )
    if rule_summary:
        st.subheader("Rule execution")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Rule": rule_code,
                        "Customers evaluated": values["evaluated"],
                        "Signals": values["alerts"],
                        "Customers skipped (UNSET)": sum(
                            values["skipped_unset"].values()
                        ),
                        "Runtime (ms)": values["elapsed_ms"],
                    }
                    for rule_code, values in rule_summary.items()
                ]
            ),
            hide_index=True,
            alt="Evaluation counts, signals, skipped customers, and runtime by rule",
        )
    st.caption(
        "A demo signal means a score of at least 0.50. It is an inspection aid, "
        "not validation of a production threshold."
    )

with customers_tab:
    st.dataframe(
        pd.DataFrame(inventory["customer_rows"]),
        hide_index=True,
        alt="Synthetic demo customers and their account counts",
    )

with accounts_tab:
    st.dataframe(
        pd.DataFrame(inventory["account_rows"]),
        hide_index=True,
        alt="Synthetic demo accounts linked to their customers",
    )

with transactions_tab:
    st.dataframe(
        pd.DataFrame(inventory["transaction_rows"]),
        hide_index=True,
        alt="Synthetic demo transactions, counterparties, and timestamps",
    )
