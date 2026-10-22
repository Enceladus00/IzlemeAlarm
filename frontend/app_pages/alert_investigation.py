import pandas as pd
import streamlit as st

from components.common import page_header, render_transaction_table
from utils.api import ApiError, api_request, show_api_error


page_header(
    "Alert investigation",
    "Review detections, inspect related transfers and customer activity, and document decisions.",
)

try:
    rules = api_request("GET", "/rules")
    rule_options = ["All rules", *[rule["rule_code"] for rule in rules]]
    with st.form("alert-filters"):
        filter_cols = st.columns(5)
        status = filter_cols[0].selectbox(
            "Status",
            ["All statuses", "new", "in_review", "closed", "confirmed_suspicious"],
        )
        severity = filter_cols[1].selectbox(
            "Severity", ["All severities", "low", "medium", "high"]
        )
        rule_code = filter_cols[2].selectbox("Rule", rule_options)
        date_from = filter_cols[3].date_input("Created from", value=None)
        date_to = filter_cols[4].date_input("Created to", value=None)
        st.form_submit_button("Apply filters", type="primary")

    params: dict[str, str | int] = {"limit": 200}
    if status != "All statuses":
        params["status"] = status
    if severity != "All severities":
        params["severity"] = severity
    if rule_code != "All rules":
        params["rule_code"] = rule_code
    if date_from:
        params["date_from"] = date_from.isoformat()
    if date_to:
        params["date_to"] = date_to.isoformat()
    if date_from and date_to and date_from > date_to:
        st.error("The start date must not be after the end date.")
    else:
        result = api_request("GET", "/alerts", params=params)
        alerts = result["items"]
        st.caption(f"{result['total']:,} matching alerts · showing up to 200")

        if not alerts:
            st.info("No alerts match the selected filters.")
        else:
            alert_by_id = {row["alert_id"]: row for row in alerts}
            table = pd.DataFrame(alerts)
            st.dataframe(
                table[
                    [
                        "alert_id",
                        "severity",
                        "rule_code",
                        "customer_name",
                        "transaction_count",
                        "status",
                        "created_at",
                    ]
                ].rename(
                    columns={
                        "alert_id": "Alert",
                        "severity": "Severity",
                        "rule_code": "Rule",
                        "customer_name": "Customer",
                        "transaction_count": "Transfers",
                        "status": "Status",
                        "created_at": "Created",
                    }
                ),
                hide_index=True,
                alt="Filtered alert investigation queue",
            )
            selected_id = st.selectbox(
                "Open alert",
                list(alert_by_id),
                format_func=lambda alert_id: (
                    f"#{alert_id} · {alert_by_id[alert_id]['severity'].upper()} · "
                    f"{alert_by_id[alert_id]['rule_code']} · "
                    f"{alert_by_id[alert_id]['customer_name']}"
                ),
            )
            detail = api_request("GET", f"/alerts/{selected_id}")
            st.divider()
            st.subheader(f"Alert #{detail['alert_id']} · {detail['rule_name']}")
            st.write(
                f"**Customer:** {detail['customer_name']} ({detail['customer_no']})  \n"
                f"**Severity:** {detail['severity']} · **Status:** {detail['status']}  \n"
                f"**Created:** {detail['created_at']}"
            )

            transaction_col, history_col = st.columns([1.3, 1])
            with transaction_col:
                st.markdown("**Associated transactions**")
                render_transaction_table(
                    detail["transactions"],
                    alt="Transactions associated with this alert",
                )
            with history_col:
                st.markdown("**Analyst history**")
                if detail["history"]:
                    st.dataframe(
                        pd.DataFrame(detail["history"]),
                        hide_index=True,
                        alt="Status changes and analyst notes for this alert",
                    )
                else:
                    st.info("No analyst actions have been recorded.")

            history_key = f"history-alert-{selected_id}"
            if st.button(
                "Load customer transaction history",
                icon=":material/manage_search:",
                key=f"load-{history_key}",
            ):
                st.session_state["loaded_customer_history"] = selected_id
            if st.session_state.get("loaded_customer_history") == selected_id:
                customer_history = api_request(
                    "GET", f"/customers/{detail['customer_no']}/transactions"
                )
                st.markdown(
                    f"**Transaction history · {customer_history['customer_name']}**"
                )
                render_transaction_table(
                    customer_history["items"],
                    alt="Recent incoming and outgoing transactions for this customer",
                )

            with st.form(f"status-{selected_id}"):
                status_options = [
                    "new",
                    "in_review",
                    "closed",
                    "confirmed_suspicious",
                ]
                new_status = st.selectbox(
                    "Update status",
                    status_options,
                    index=status_options.index(detail["status"]),
                )
                note = st.text_area(
                    "Analyst reasoning",
                    placeholder="Record evidence, context, or why this alert is being resolved.",
                )
                if st.form_submit_button("Save investigation update", type="primary"):
                    try:
                        api_request(
                            "PATCH",
                            f"/alerts/{selected_id}/status",
                            json={"status": new_status, "note": note or None},
                        )
                        st.success("Alert status and analyst note saved.")
                        st.rerun()
                    except ApiError as error:
                        show_api_error(error)
except ApiError as error:
    show_api_error(error)
