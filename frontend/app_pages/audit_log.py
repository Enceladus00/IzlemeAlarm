import pandas as pd
import streamlit as st

from components.common import page_header
from utils.api import ApiError, api_request, show_api_error


page_header(
    "Audit log",
    "Review authentication, access-control, upload, rule, and alert events.",
)

try:
    result = api_request("GET", "/audit-log", params={"limit": 200})
    st.caption(f"{result['total']:,} events · showing up to 200")
    if result["items"]:
        st.dataframe(
            pd.DataFrame(result["items"]),
            hide_index=True,
            alt="Application audit events",
        )
    else:
        st.info("No audit events have been recorded.")
except ApiError as error:
    show_api_error(error)
