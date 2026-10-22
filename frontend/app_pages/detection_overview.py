from datetime import date

import pandas as pd
import streamlit as st

from components.common import metric_row, page_header
from utils.api import ApiError, api_request, show_api_error


page_header(
    "Detection overview",
    "A live view of analyzed activity, suspicious transactions, and rule outcomes.",
)

try:
    summary = api_request("GET", "/dashboard/summary")
    alert_counts = summary["by_status"]
    metric_row(
        [
            ("Transactions analyzed", f"{summary['transactions']:,}"),
            ("Suspicious transactions", f"{summary['suspicious_transactions']:,}"),
            ("Alerts", f"{summary['alerts']:,}"),
            ("Customers monitored", f"{summary['customers']:,}"),
        ]
    )

    trend_col, severity_col = st.columns([1.6, 1])
    with trend_col:
        with st.container(border=True):
            st.subheader("Detection trends · last 30 days")
            trend = pd.DataFrame(summary["trends"])
            if not trend.empty:
                trend["date"] = pd.to_datetime(trend["date"])
                st.line_chart(
                    trend.set_index("date")[["alerts", "suspicious_transactions"]],
                    alt="Daily alert and suspicious transaction counts for the last 30 days",
                )
            else:
                st.info("No detection trend data is available.")
    with severity_col:
        with st.container(border=True):
            st.subheader("Alert severity")
            severity = pd.DataFrame(
                [
                    {"Severity": level.title(), "Alerts": count}
                    for level, count in summary["by_severity"].items()
                ]
            )
            if severity.empty:
                st.info("No alerts have been generated yet.")
            else:
                st.bar_chart(
                    severity,
                    x="Severity",
                    y="Alerts",
                    alt="Alerts grouped by severity",
                )
            st.caption(
                f"Open alerts: {sum(count for status, count in alert_counts.items() if status in {'new', 'in_review'}):,}"
            )

    rules_col, activity_col = st.columns([1, 1.4])
    with rules_col:
        with st.container(border=True):
            st.subheader("Most frequently triggered rules")
            rule_counts = sorted(
                summary["by_rule"].items(), key=lambda item: item[1], reverse=True
            )
            rule_frame = pd.DataFrame(
                [
                    {"Rule": code, "Triggered alerts": count}
                    for code, count in rule_counts
                ]
            )
            if rule_frame.empty:
                st.info("No monitoring rules are configured.")
            else:
                st.bar_chart(
                    rule_frame,
                    x="Rule",
                    y="Triggered alerts",
                    alt="Alert counts by monitoring rule",
                )

    with activity_col:
        with st.container(border=True):
            st.subheader("Latest alerts")
            latest = api_request("GET", "/alerts", params={"limit": 8})
            if latest["items"]:
                frame = pd.DataFrame(latest["items"])
                visible = frame[
                    [
                        "alert_id",
                        "rule_code",
                        "customer_name",
                        "severity",
                        "status",
                        "created_at",
                    ]
                ].rename(
                    columns={
                        "alert_id": "Alert",
                        "rule_code": "Rule",
                        "customer_name": "Customer",
                        "severity": "Severity",
                        "status": "Status",
                        "created_at": "Created",
                    }
                )
                st.dataframe(visible, hide_index=True, alt="Most recently created alerts")
            else:
                st.info("No alerts yet. Run the rules to evaluate available transactions.")

    action_col, date_col = st.columns([1, 3], vertical_alignment="center")
    with action_col:
        if st.button("Evaluate rules now", type="primary"):
            result = api_request("POST", "/rules/evaluate")
            st.success(f"{result['created_alerts']} new alerts created.")
            st.rerun()
    with date_col:
        st.caption(f"Reporting date: {date.today():%b %d, %Y}")
except ApiError as error:
    show_api_error(error)
