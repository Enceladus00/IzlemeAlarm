import pandas as pd
import streamlit as st

from components.common import page_header
from utils.api import ApiError, api_request, show_api_error


page_header(
    "Data management",
    "Validate and import customer, account, and transaction CSV files.",
)

entity = st.selectbox("Data type", ["customer", "account", "transaction"])
templates = {
    "customer": (
        "customer_no,full_name,customer_type,occupation,monthly_income,risk_level\n"
        "DEMO-NEW-001,Example Customer,person,Engineer,50000,low\n"
    ),
    "account": (
        "account_no,customer_no,currency,account_type,opened_at\n"
        "DEMO-NEW-ACC-001,DEMO-001,TRY,current,2026-01-01\n"
    ),
    "transaction": (
        "transaction_no,sender_account_no,receiver_account_no,amount,currency,"
        "tx_time,channel,country_code\n"
        "NEW-TX-001,DEMO-ACC-001,DEMO-ACC-002,1250,TRY,"
        "2026-01-01T10:00:00,mobile,US\n"
    ),
}
st.download_button(
    "Download CSV template",
    templates[entity].encode("utf-8"),
    file_name=f"{entity}_template.csv",
    mime="text/csv",
)
file = st.file_uploader("CSV file", type=["csv"])
if file is not None and st.button("Validate and upload", type="primary"):
    try:
        result = api_request(
            "POST",
            "/uploads",
            params={"entity": entity},
            files={"file": (file.name, file.getvalue(), "text/csv")},
        )
        st.session_state["last_upload_id"] = result["batch_id"]
        st.success(
            f"Upload #{result['batch_id']}: {result['accepted_rows']} accepted, "
            f"{result['rejected_rows']} rejected ({result['total_rows']} rows)."
        )
        if result["errors"]:
            st.dataframe(
                pd.DataFrame(result["errors"]),
                hide_index=True,
                alt="Rows rejected during CSV upload",
            )
    except ApiError as error:
        show_api_error(error)

batch_id = st.number_input(
    "Previous upload report · batch ID",
    min_value=1,
    step=1,
    value=int(st.session_state.get("last_upload_id", 1)),
)
if st.button("Load upload report"):
    try:
        report = api_request("GET", f"/uploads/{batch_id}")
        st.json(report)
    except ApiError as error:
        show_api_error(error)
