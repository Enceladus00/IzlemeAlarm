from typing import Any

import streamlit as st

from components.common import page_header
from utils.api import ApiError, api_request, show_api_error


page_header(
    "Rule management",
    "Review and adjust validated R1–R4 monitoring thresholds.",
)

try:
    rules = api_request("GET", "/rules")
    if not rules:
        st.info("No monitoring rules are configured.")
    else:
        can_edit = "rule:edit" in st.session_state.get("permissions", [])
        if not can_edit:
            st.info("Rule settings are read-only for your account.")
        labels = [f"{item['rule_code']} — {item['name']}" for item in rules]
        selected_label = st.selectbox("Rule", labels)
        selected = rules[labels.index(selected_label)]
        st.write(selected["description"])
        thresholds = selected["thresholds"]
        with st.form(f"rule-{selected['rule_code']}"):
            active = st.checkbox(
                "Rule active",
                value=selected["is_active"],
                disabled=not can_edit,
            )
            values: dict[str, Any] = {}
            if selected["rule_code"] == "R1":
                values["amount_limit"] = st.number_input(
                    "Transaction threshold",
                    min_value=0.01,
                    value=float(thresholds["amount_limit"]),
                    step=100.0,
                    disabled=not can_edit,
                )
                values["proximity_percent"] = st.number_input(
                    "Near-threshold range (%)",
                    min_value=0.01,
                    max_value=99.99,
                    value=float(thresholds["proximity_percent"]),
                    step=1.0,
                    disabled=not can_edit,
                )
                values["transaction_count"] = st.number_input(
                    "Minimum transfers",
                    min_value=2,
                    value=int(thresholds["transaction_count"]),
                    step=1,
                    disabled=not can_edit,
                )
                values["window_minutes"] = st.number_input(
                    "Time window (minutes)",
                    min_value=1,
                    value=int(thresholds["window_minutes"]),
                    step=1,
                    disabled=not can_edit,
                )
            elif selected["rule_code"] == "R2":
                values["outflow_ratio"] = st.number_input(
                    "Minimum outflow / inflow ratio",
                    min_value=0.01,
                    max_value=1.0,
                    value=float(thresholds["outflow_ratio"]),
                    step=0.05,
                    disabled=not can_edit,
                )
                values["window_minutes"] = st.number_input(
                    "Time window (minutes)",
                    min_value=1,
                    value=int(thresholds["window_minutes"]),
                    step=1,
                    disabled=not can_edit,
                )
            elif selected["rule_code"] == "R3":
                values["average_multiplier"] = st.number_input(
                    "Average amount multiplier",
                    min_value=0.01,
                    value=float(thresholds["average_multiplier"]),
                    step=0.5,
                    disabled=not can_edit,
                )
                values["minimum_history_count"] = st.number_input(
                    "Required history transfers",
                    min_value=1,
                    value=int(thresholds["minimum_history_count"]),
                    step=1,
                    disabled=not can_edit,
                )
            else:
                values["enabled"] = st.checkbox(
                    "R4 country matching enabled",
                    value=bool(thresholds["enabled"]),
                    disabled=not can_edit,
                )
                values["countries"] = [
                    country.strip().upper()
                    for country in st.text_input(
                        "Demo ISO country codes (comma separated)",
                        value=", ".join(thresholds["countries"]),
                        disabled=not can_edit,
                    ).split(",")
                    if country.strip()
                ]
                st.caption(
                    "Demo defaults are TR and IL; these are not real-world risk classifications."
                )
            if st.form_submit_button(
                "Save rule",
                type="primary",
                disabled=not can_edit,
            ):
                try:
                    api_request(
                        "PUT",
                        f"/rules/{selected['rule_code']}",
                        json={"is_active": active, "thresholds": values},
                    )
                    st.success("Rule settings saved.")
                    st.rerun()
                except ApiError as error:
                    show_api_error(error)
except ApiError as error:
    show_api_error(error)
