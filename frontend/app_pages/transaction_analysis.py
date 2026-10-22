from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st

from components.common import metric_row, page_header
from components.transaction_flow import build_account_flow_svg
from utils.api import ApiError, api_request, show_api_error


page_header(
    "Transaction analysis",
    "Trace money movement, compare transfer patterns, and inspect unusual activity.",
)

with st.form("transaction-filters"):
    identity_col, direction_col, from_col = st.columns(3)
    customer_no = identity_col.text_input(
        "Customer number",
        placeholder="Optional; required for a direction filter",
    ).strip()
    direction_label = direction_col.selectbox(
        "Direction", ["All activity", "Incoming", "Outgoing"]
    )
    date_from = from_col.date_input("From", value=None)
    to_col, minimum_col, maximum_col = st.columns(3)
    date_to = to_col.date_input("To", value=None)
    minimum_amount = minimum_col.number_input(
        "Minimum amount", min_value=0.0, value=0.0, step=100.0
    )
    maximum_amount = maximum_col.number_input(
        "Maximum amount", min_value=0.0, value=0.0, step=100.0
    )
    st.form_submit_button("Analyze transactions", type="primary")

if date_from and date_to and date_from > date_to:
    st.error("The start date must not be after the end date.")
elif minimum_amount > 0 and maximum_amount > 0 and minimum_amount > maximum_amount:
    st.error("The minimum amount must not exceed the maximum amount.")
elif direction_label != "All activity" and not customer_no:
    st.info("Enter a customer number to analyze incoming or outgoing direction.")
else:
    params: dict[str, Any] = {"limit": 500}
    if customer_no:
        params["customer_no"] = customer_no
    if direction_label != "All activity":
        params["direction"] = direction_label.lower()
    if date_from:
        params["date_from"] = date_from.isoformat()
    if date_to:
        params["date_to"] = date_to.isoformat()
    if minimum_amount > 0:
        params["min_amount"] = minimum_amount
    if maximum_amount > 0:
        params["max_amount"] = maximum_amount

    try:
        result = api_request("GET", "/transactions", params=params)
        transactions = result["items"]
        st.caption(
            f"{result['total']:,} matching transactions · "
            f"showing up to {len(transactions):,}"
        )
        if not transactions:
            st.info("No transactions match the selected filters.")
        else:
            frame = pd.DataFrame(transactions)
            frame["tx_time"] = pd.to_datetime(frame["tx_time"])
            frame["amount_numeric"] = pd.to_numeric(frame["amount"])
            frame["date"] = frame["tx_time"].dt.date

            outgoing = frame.groupby("currency")["amount_numeric"].sum()
            incoming = frame.groupby("currency")["amount_numeric"].sum()
            if customer_no:
                outgoing = frame.loc[
                    frame["sender_customer_no"] == customer_no
                ].groupby("currency")["amount_numeric"].sum()
                incoming = frame.loc[
                    frame["receiver_customer_no"] == customer_no
                ].groupby("currency")["amount_numeric"].sum()

            def format_currency_totals(totals: pd.Series) -> str:
                if totals.empty:
                    return "0"
                return " · ".join(
                    f"{amount:,.2f} {currency}"
                    for currency, amount in totals.items()
                )

            metric_row(
                [
                    ("Transfers in view", f"{len(frame):,}"),
                    ("Incoming value", format_currency_totals(incoming)),
                    ("Outgoing value", format_currency_totals(outgoing)),
                    ("Unique accounts", f"{pd.concat([frame['sender_account_no'], frame['receiver_account_no']]).nunique():,}"),
                ]
            )

            frame["flagged"] = frame["alert_linked"]

            chart_col, transfer_col = st.columns([1, 1])
            with chart_col:
                with st.container(border=True):
                    st.subheader("Incoming vs. outgoing")
                    flow_rows: list[dict[str, Any]] = []
                    for row in transactions:
                        amount = float(row["amount"])
                        if customer_no:
                            if row["sender_customer_no"] == customer_no:
                                flow_rows.append(
                                    {
                                        "Direction": "Outgoing",
                                        "Currency": row["currency"],
                                        "Transfers": 1,
                                        "Value": amount,
                                    }
                                )
                            if row["receiver_customer_no"] == customer_no:
                                flow_rows.append(
                                    {
                                        "Direction": "Incoming",
                                        "Currency": row["currency"],
                                        "Transfers": 1,
                                        "Value": amount,
                                    }
                                )
                        else:
                            flow_rows.extend(
                                [
                                    {
                                        "Direction": "Outgoing",
                                        "Currency": row["currency"],
                                        "Transfers": 1,
                                        "Value": amount,
                                    },
                                    {
                                        "Direction": "Incoming",
                                        "Currency": row["currency"],
                                        "Transfers": 1,
                                        "Value": amount,
                                    },
                                ]
                            )
                    flow_frame = pd.DataFrame(flow_rows)
                    if not flow_frame.empty:
                        flow_counts = (
                            flow_frame.groupby(["Direction", "Currency"], as_index=False)
                            .agg(Transfers=("Transfers", "sum"))
                        )
                        st.bar_chart(
                            flow_counts,
                            x="Direction",
                            y="Transfers",
                            color="Currency",
                            stack=True,
                            alt="Incoming and outgoing transfer counts by currency",
                        )
                        st.caption(
                            "Transfer values are kept separate by currency; no FX conversion is applied."
                        )
            with transfer_col:
                with st.container(border=True):
                    st.subheader("Activity timeline")
                    daily = (
                        frame.groupby("date", as_index=False)
                        .agg(Transfers=("transaction_id", "count"))
                    )
                    st.bar_chart(
                        daily,
                        x="date",
                        y="Transfers",
                        alt="Transaction count by day",
                    )

            with st.container(border=True):
                st.subheader("Account movement")
                entity_names: set[tuple[str, str, str]] = set()
                for transaction in transactions:
                    entity_names.add(
                        (
                            "customer",
                            transaction["sender_customer_no"],
                            transaction["sender_customer_name"],
                        )
                    )
                    entity_names.add(
                        (
                            "customer",
                            transaction["receiver_customer_no"],
                            transaction["receiver_customer_name"],
                        )
                    )
                    entity_names.add(
                        (
                            "account",
                            transaction["sender_account_no"],
                            transaction["sender_customer_name"],
                        )
                    )
                    entity_names.add(
                        (
                            "account",
                            transaction["receiver_account_no"],
                            transaction["receiver_customer_name"],
                        )
                    )
                entities = sorted(
                    entity_names,
                    key=lambda entity: (
                        entity[0],
                        entity[2].casefold(),
                        entity[1],
                    ),
                )
                focus = st.selectbox(
                    "Show transfer links for",
                    [None, *entities],
                    format_func=lambda entity: (
                        "Choose a customer or account"
                        if entity is None
                        else (
                            f"Customer: {entity[2]} ({entity[1]})"
                            if entity[0] == "customer"
                            else f"Account: {entity[1]} · {entity[2]}"
                        )
                    ),
                    key="account-flow-focus",
                )
                if focus is None:
                    st.info(
                        "Choose a customer or account to see only its incoming "
                        "and outgoing transfer links."
                    )
                else:
                    focus_type, focus_id, focus_name = focus
                    flow_params = {
                        name: value
                        for name, value in params.items()
                        if name not in {"customer_no", "direction", "limit"}
                    }
                    flow_params["limit"] = 500
                    flow_params[
                        "customer_no" if focus_type == "customer" else "account_no"
                    ] = focus_id
                    if direction_label != "All activity":
                        flow_params["direction"] = direction_label.lower()

                    with st.spinner(f"Loading all transfers for {focus_name}..."):
                        flow_result = api_request(
                            "GET", "/transactions", params=flow_params
                        )
                        focused_transactions = list(flow_result["items"])
                        flow_total = flow_result["total"]
                        while len(focused_transactions) < flow_total:
                            flow_params["offset"] = len(focused_transactions)
                            next_page = api_request(
                                "GET", "/transactions", params=flow_params
                            )
                            if not next_page["items"]:
                                raise ApiError(
                                    "The API returned an incomplete transfer history "
                                    f"for {focus_name}."
                                )
                            focused_transactions.extend(next_page["items"])

                    flow_svg, involved_accounts, visible_routes = (
                        build_account_flow_svg(
                            focused_transactions,
                            focus_type,
                            focus_id,
                        )
                    )
                    if flow_svg:
                        st.iframe(
                            flow_svg,
                            height=610,
                            alt=f"Transfer links for {focus_name}",
                        )
                        st.caption(
                            f"Showing all {len(focused_transactions):,} matching "
                            f"transfers for {focus_name}: {visible_routes:,} "
                            f"currency-specific routes across {involved_accounts:,} "
                            "accounts. Band thickness indicates transfer frequency; "
                            "red routes include alert-linked transfers."
                        )
                    else:
                        st.info(
                            "No transfers match this focus and the selected filters."
                        )

            with st.container(border=True):
                with st.container(border=True):
                    st.subheader("Repeated transfers near thresholds")
                    rule_data = api_request("GET", "/rules")
                    r1 = next(
                        (
                            rule
                            for rule in rule_data
                            if rule["rule_code"] == "R1" and rule["is_active"]
                        ),
                        None,
                    )
                    if r1:
                        thresholds = r1["thresholds"]
                        ceiling = Decimal(str(thresholds["amount_limit"]))
                        lower_bound = ceiling * (
                            Decimal(100 - float(thresholds["proximity_percent"]))
                            / Decimal(100)
                        )
                        near = frame[
                            (frame["sender_customer_no"].notna())
                            & (frame["currency"].notna())
                            & (frame["amount_numeric"] >= float(lower_bound))
                            & (frame["amount_numeric"] < float(ceiling))
                        ]
                        if near.empty:
                            st.info("No transfers fall within the active R1 near-limit range.")
                        else:
                            grouped = (
                                near.groupby(
                                    ["sender_customer_name", "currency"],
                                    as_index=False,
                                )
                                .agg(
                                    Transfers=("transaction_id", "count"),
                                    Minimum=("amount_numeric", "min"),
                                    Maximum=("amount_numeric", "max"),
                                )
                                .sort_values("Transfers", ascending=False)
                            )
                            st.dataframe(
                                grouped,
                                hide_index=True,
                                alt="Outgoing transactions close to the configured R1 threshold",
                            )
                            st.caption(
                                f"R1 range: {lower_bound:,.2f} to below "
                                f"{ceiling:,.2f} per transaction. This is a pattern "
                                "indicator, not a separate alert."
                            )
                    else:
                        st.info("Activate rule R1 to inspect its near-limit range.")

            st.subheader("Transfers")
            table = frame[
                [
                    "transaction_no",
                    "tx_time",
                    "amount",
                    "currency",
                    "sender_customer_name",
                    "sender_account_no",
                    "receiver_customer_name",
                    "receiver_account_no",
                    "country_code",
                    "channel",
                    "flagged",
                ]
            ].rename(
                columns={
                    "transaction_no": "Transaction",
                    "tx_time": "Time",
                    "amount": "Amount",
                    "currency": "Currency",
                    "sender_customer_name": "From customer",
                    "sender_account_no": "From account",
                    "receiver_customer_name": "To customer",
                    "receiver_account_no": "To account",
                    "country_code": "Country",
                    "channel": "Channel",
                    "flagged": "Alert linked",
                }
            )
            st.dataframe(
                table,
                hide_index=True,
                alt="Filtered transfers with associated alert indicators",
            )
    except ApiError as error:
        show_api_error(error)
