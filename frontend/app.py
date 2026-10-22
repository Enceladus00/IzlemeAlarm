import streamlit as st

from utils.api import ApiError, api_request, show_api_error


st.set_page_config(
    page_title="Sentinel · Transaction Monitoring",
    page_icon=":material/shield:",
    layout="wide",
)

pages = st.navigation(
    {
        "Monitoring": [
            st.Page(
                "app_pages/detection_overview.py",
                title="Detection overview",
                icon=":material/dashboard:",
                default=True,
            ),
            st.Page(
                "app_pages/alert_investigation.py",
                title="Alert investigation",
                icon=":material/search:",
            ),
            st.Page(
                "app_pages/transaction_analysis.py",
                title="Transaction analysis",
                icon=":material/account_tree:",
            ),
        ],
        "Operations": [
            st.Page(
                "app_pages/data_upload.py",
                title="Data management",
                icon=":material/upload_file:",
            ),
            st.Page(
                "app_pages/rule_management.py",
                title="Rule management",
                icon=":material/tune:",
            ),
        ],
    }
)

with st.sidebar:
    st.title("Sentinel")
    st.caption("Transaction monitoring")
    st.divider()
    if st.button(
        "Load demo data",
        type="secondary",
        icon=":material/database:",
        width="stretch",
    ):
        try:
            result = api_request("POST", "/demo/seed")
            st.success(
                f"Demo ready: {result['customers']} customers, "
                f"{result['transactions']} transactions; "
                f"{result['created_alerts']} new alerts."
            )
        except ApiError as error:
            show_api_error(error)
    st.caption("Use synthetic data for evaluation and demonstrations.")

pages.run()
    