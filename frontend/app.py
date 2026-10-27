import os

import streamlit as st

from utils.api import ApiError, api_request, show_api_error


st.set_page_config(
    page_title="Sentinel · Transaction Monitoring",
    page_icon=":material/shield:",
    layout="wide",
)

st.session_state.setdefault("permissions", [])

if not st.session_state.get("auth_token"):
    st.title("Sentinel sign in")
    st.caption("Sign in with your monitoring-system account.")
    with st.form("login-form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        try:
            token_result = api_request(
                "POST",
                "/auth/login",
                data={"username": username, "password": password},
            )
            st.session_state["auth_token"] = token_result["access_token"]
            profile = api_request("GET", "/auth/me")
            st.session_state["current_user"] = profile["username"]
            st.session_state["permissions"] = profile["permissions"]
            st.rerun()
        except ApiError as error:
            show_api_error(error)
else:
    try:
        profile = api_request("GET", "/auth/me")
        st.session_state["current_user"] = profile["username"]
        st.session_state["permissions"] = profile["permissions"]
    except ApiError as error:
        show_api_error(error)
        st.stop()

    permissions = set(st.session_state.get("permissions", []))
    page_groups: dict[str, list[st.Page]] = {}

    def add_page(
        section: str,
        path: str,
        title: str,
        icon: str,
        permission: str,
    ) -> None:
        if permission in permissions:
            page_groups.setdefault(section, []).append(
                st.Page(path, title=title, icon=icon)
            )

    add_page(
        "Monitoring",
        "app_pages/detection_overview.py",
        "Detection overview",
        ":material/dashboard:",
        "dashboard:view",
    )
    add_page(
        "Monitoring",
        "app_pages/alert_investigation.py",
        "Alert investigation",
        ":material/search:",
        "alert:view",
    )
    add_page(
        "Monitoring",
        "app_pages/transaction_analysis.py",
        "Transaction analysis",
        ":material/account_tree:",
        "customer:view",
    )
    add_page(
        "Operations",
        "app_pages/data_upload.py",
        "Data management",
        ":material/upload_file:",
        "upload:create" if "upload:create" in permissions else "upload:view",
    )
    add_page(
        "Operations",
        "app_pages/rule_management.py",
        "Rule management",
        ":material/tune:",
        "rule:view",
    )
    add_page(
        "Administration",
        "app_pages/user_management.py",
        "User management",
        ":material/group:",
        "user:manage",
    )
    add_page(
        "Administration",
        "app_pages/audit_log.py",
        "Audit log",
        ":material/history:",
        "audit:view",
    )

    if not page_groups:
        st.warning("Your account has no active application permissions.")
        st.stop()

    with st.sidebar:
        st.title("Sentinel")
        st.caption(f"Signed in as {st.session_state.get('current_user', '')}")
        if st.button("Sign out", width="stretch"):
            for key in ("auth_token", "permissions", "current_user"):
                st.session_state.pop(key, None)
            st.rerun()
        if (
            "upload:create" in permissions
            and os.getenv("ENABLE_DEMO_ENDPOINTS", "").lower() == "true"
        ):
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
                        f"{result['transactions']} new scenario transactions; "
                        f"{result['created_alerts']} new alerts."
                    )
                    st.caption(
                        "Demo-only PROVISIONAL thresholds are run for synthetic "
                        "customers; saved rule settings remain unchanged. R02 is "
                        "stored as an INFO signal, not an alert."
                    )
                except ApiError as error:
                    show_api_error(error)
            st.caption("Use synthetic data for evaluation and demonstrations.")

    pages = st.navigation(page_groups)
    pages.run()
    