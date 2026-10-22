from collections.abc import Sequence
from typing import Any

import pandas as pd
import streamlit as st


def page_header(title: str, description: str) -> None:
    st.title(title)
    st.caption(description)


def metric_row(metrics: Sequence[tuple[str, Any]]) -> None:
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value, border=True)


def render_transaction_table(
    transactions: list[dict[str, Any]],
    *,
    alt: str = "Transaction records",
) -> None:
    if not transactions:
        st.info("No transactions to display.")
        return
    frame = pd.DataFrame(transactions)
    columns = [
        column
        for column in (
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
        )
        if column in frame
    ]
    labels = {
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
    }
    st.dataframe(
        frame[columns].rename(columns=labels),
        hide_index=True,
        alt=alt,
    )
