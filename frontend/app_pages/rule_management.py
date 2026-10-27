from decimal import Decimal
from typing import Any

import streamlit as st

from components.common import page_header
from utils.api import ApiError, api_request, show_api_error


CUSTOMER_TYPES = ("BIREYSEL", "KURUMSAL")
PARAMETER_STATUSES = ("UNSET", "PROVISIONAL", "APPROVED")
STATUS_LABELS = {
    "UNSET": "Not configured",
    "PROVISIONAL": "Provisional",
    "APPROVED": "Approved",
}
CHANNEL_LABELS = {
    "atm": "ATM",
    "mobile": "Mobile app",
    "internet": "Internet banking",
    "branch": "Branch",
}


def _currency_inputs(
    rule_code: str,
    customer_type: str,
    existing_limits: dict[str, Any],
    *,
    editable: bool,
) -> dict[str, float] | None:
    st.markdown("**Transaction limits by currency**")
    st.caption(
        "Enter one currency code and its limit per row. Leave unused rows empty. "
        "Currencies without a limit are ignored; no currency conversion is applied."
    )
    existing = [
        (currency, float(amount))
        for currency, amount in sorted(existing_limits.items())
    ]
    row_count = max(3, len(existing) + 1)
    limits: dict[str, float] = {}
    invalid = False

    for row_index in range(row_count):
        currency_default, amount_default = (
            existing[row_index] if row_index < len(existing) else ("", None)
        )
        currency_column, amount_column = st.columns([1, 2])
        currency = currency_column.text_input(
            "Currency code" if row_index == 0 else f"Currency code {row_index + 1}",
            value=currency_default,
            max_chars=3,
            key=f"{rule_code}-{customer_type}-currency-{row_index}",
            help="Three-letter uppercase code, for example TRY, USD, or EUR.",
            disabled=not editable,
        ).strip().upper()
        amount = amount_column.number_input(
            "Limit amount" if row_index == 0 else f"Limit amount {row_index + 1}",
            min_value=0.0,
            value=amount_default,
            step=100.0,
            format="%.2f",
            key=f"{rule_code}-{customer_type}-limit-{row_index}",
            help="Must be greater than zero when a currency code is entered.",
            disabled=not editable,
        )

        if not currency and amount in (None, 0):
            continue
        if not currency:
            st.error(f"Add a currency code for limit row {row_index + 1}.")
            invalid = True
        elif len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            st.error(
                f"Currency code in row {row_index + 1} must be a three-letter code, such as TRY or USD."
            )
            invalid = True
        elif currency in limits:
            st.error(f"Currency {currency} is listed more than once.")
            invalid = True
        elif amount is None or amount <= 0:
            st.error(f"Limit for {currency} must be greater than zero.")
            invalid = True
        else:
            limits[currency] = amount

    if not limits and not invalid:
        st.error("Add at least one currency and its limit before saving.")
        invalid = True
    return None if invalid else limits


def _parameter_inputs(
    rule_code: str,
    customer_type: str,
    values: dict[str, Any],
    *,
    editable: bool,
) -> dict[str, Any] | None:
    limits = _currency_inputs(
        rule_code,
        customer_type,
        values.get("limits", {}),
        editable=editable,
    )
    result: dict[str, Any] = {"limits": limits or {}}
    invalid = limits is None
    if rule_code in {"R01", "R03"}:
        first_column, second_column = st.columns(2)
        x_esik_default = values.get("x_esik")
        x_kesin_default = values.get("x_kesin")
        result["x_esik"] = first_column.number_input(
            "Starting count (x_esik)",
            min_value=0,
            value=(
                int(Decimal(str(x_esik_default)))
                if x_esik_default is not None
                else None
            ),
            step=1,
            key=f"{rule_code}-{customer_type}-x-esik",
            help="At this count, the rule score is 0.5.",
            disabled=not editable,
        )
        result["x_kesin"] = second_column.number_input(
            "High-confidence count (x_kesin)",
            min_value=1,
            value=(
                max(1, int(Decimal(str(x_kesin_default))))
                if x_kesin_default is not None
                else None
            ),
            step=1,
            key=f"{rule_code}-{customer_type}-x-kesin",
            help="At this count, the rule score is 0.9. It must be greater than the starting count.",
            disabled=not editable,
        )
        if result["x_esik"] is None or result["x_kesin"] is None:
            st.error("Enter both score counts.")
            invalid = True
        elif result["x_kesin"] <= result["x_esik"]:
            st.error("The high-confidence count must exceed the starting count.")
            invalid = True

    if rule_code == "R01":
        ratio_column, currency_column = st.columns(2)
        income_ratio_default = values.get("minimum_income_ratio")
        result["minimum_income_ratio"] = ratio_column.number_input(
            "Minimum transaction total / monthly income",
            min_value=0.0001,
            value=(
                float(Decimal(str(income_ratio_default)))
                if income_ratio_default is not None
                else None
            ),
            step=0.01,
            format="%.4f",
            key=f"{rule_code}-{customer_type}-income-ratio",
            help="For example, 0.45 means 45% of monthly income. Set the value approved for your institution.",
            disabled=not editable,
        )
        result["income_currency"] = currency_column.text_input(
            "Monthly income currency",
            value=str(values.get("income_currency", "")),
            max_chars=3,
            key=f"{rule_code}-{customer_type}-income-currency",
            help="Currency of the customer's monthly income; no conversion is performed.",
            disabled=not editable,
        ).strip().upper()
        if result["minimum_income_ratio"] is None:
            st.error("Enter the approved minimum income ratio.")
            invalid = True
        if len(result["income_currency"]) != 3:
            st.error("Enter the three-letter monthly income currency code.")
            invalid = True

    if rule_code == "R03":
        selected_channels = values.get("cash_channels", [])
        channel_labels = st.multiselect(
            "Channels treated as cash deposits",
            options=list(CHANNEL_LABELS),
            default=[
                channel for channel in selected_channels if channel in CHANNEL_LABELS
            ],
            format_func=lambda channel: CHANNEL_LABELS[channel],
            key=f"{rule_code}-{customer_type}-cash-channels",
            help="Select only the channels your organization defines as cash deposits.",
            disabled=not editable,
        )
        result["cash_channels"] = channel_labels
        if not channel_labels:
            st.error("Select at least one channel treated as a cash deposit.")
            invalid = True

    return None if invalid else result


page_header(
    "Rule management",
    "Configure each rule using guided fields. No production thresholds are prefilled.",
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
        metadata = selected.get("metadata")

        if metadata is None:
            st.info(
                "This legacy rule has no registered implementation and cannot be edited. "
                "Its historical alerts and database record are retained."
            )
        else:
            with st.expander("How this rule works and what its settings mean"):
                st.markdown("**Rule steps**")
                for index, step in enumerate(metadata["steps"], 1):
                    st.markdown(f"{index}. {step}")
                st.markdown("**Parameter guide**")
                for parameter in metadata["parameters"]:
                    st.markdown(f"- **{parameter['name']}** — {parameter['meaning']}")
                st.caption(
                    "UNSET means the rule skips this customer type. PROVISIONAL values "
                    "are used with a warning. APPROVED values are institution-approved."
                )

            existing_thresholds = selected.get("thresholds") or {}
            customer_status: dict[str, str] = {}
            status_columns = st.columns(2)
            for index, customer_type in enumerate(CUSTOMER_TYPES):
                current = existing_thresholds.get(
                    customer_type, {"status": "UNSET", "values": {}}
                )
                current_status = current.get("status", "UNSET")
                customer_status[customer_type] = status_columns[index].selectbox(
                    f"{customer_type} parameter status",
                    PARAMETER_STATUSES,
                    index=PARAMETER_STATUSES.index(current_status),
                    format_func=lambda status: (
                        f"{STATUS_LABELS[status]} ({status})"
                    ),
                    key=f"{selected['rule_code']}-{customer_type}-status",
                    disabled=not can_edit,
                    help="UNSET disables this rule for the customer type.",
                )

            threshold_updates: dict[str, Any] = {}
            parameter_errors = False
            with st.form(f"rule-{selected['rule_code']}"):
                active = st.checkbox(
                    "Rule active",
                    value=selected["is_active"],
                    disabled=not can_edit,
                )
                weight = st.number_input(
                    "Combined-risk weight",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(selected.get("weight") or 0),
                    step=0.05,
                    format="%.3f",
                    disabled=not can_edit,
                    help="Saved for future combined-risk scoring; this app does not calculate R18 yet.",
                )

                customer_columns = st.columns(2)
                for index, customer_type in enumerate(CUSTOMER_TYPES):
                    current = existing_thresholds.get(
                        customer_type, {"status": "UNSET", "values": {}}
                    )
                    status = customer_status[customer_type]
                    with customer_columns[index]:
                        with st.container(border=True):
                            st.subheader(customer_type)
                            st.caption(f"Parameter status: {STATUS_LABELS[status]}")
                            if status == "UNSET":
                                st.info(
                                    "This customer type will be skipped until parameters are provided."
                                )
                                threshold_updates[customer_type] = {
                                    "status": "UNSET",
                                    "values": {},
                                }
                            else:
                                entered_values = _parameter_inputs(
                                    selected["rule_code"],
                                    customer_type,
                                    current.get("values", {}),
                                    editable=can_edit,
                                )
                                if entered_values is None:
                                    parameter_errors = True
                                else:
                                    threshold_updates[customer_type] = {
                                        "status": status,
                                        "values": entered_values,
                                    }

                submitted = st.form_submit_button(
                    "Save rule settings",
                    type="primary",
                    disabled=not can_edit,
                )
                if submitted:
                    if parameter_errors:
                        st.error("Correct the highlighted parameter fields and try again.")
                    else:
                        try:
                            api_request(
                                "PUT",
                                f"/rules/{selected['rule_code']}",
                                json={
                                    "is_active": active,
                                    "weight": weight,
                                    "thresholds": threshold_updates,
                                },
                            )
                            st.success("Rule settings saved.")
                            st.rerun()
                        except ApiError as error:
                            show_api_error(error)
except ApiError as error:
    show_api_error(error)
