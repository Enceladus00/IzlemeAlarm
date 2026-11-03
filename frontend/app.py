import time

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
            st.session_state["auth_expires_at"] = (
                time.time() + int(token_result["expires_in"])
            )
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
        "Administration",
        "app_pages/system_overview.py",
        "System overview",
        ":material/monitor_heart:",
        "user:manage",
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
        "app_pages/demo_lab.py",
        "Demo lab",
        ":material/science:",
        "dashboard:view",
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

        @st.fragment(run_every="1s")
        def render_session_countdown() -> None:
            expires_at = st.session_state.get("auth_expires_at")
            if expires_at is None:
                return
            remaining = max(0, int(expires_at - time.time()))
            if remaining == 0:
                for key in ("auth_token", "auth_expires_at", "permissions", "current_user"):
                    st.session_state.pop(key, None)
                st.warning("Your session expired. Please sign in again.")
                st.rerun()
            minutes, seconds = divmod(remaining, 60)
            st.caption(f"Session expires in {minutes:02d}:{seconds:02d}")

        render_session_countdown()
        if st.button("Sign out", width="stretch"):
            for key in (
                "auth_token",
                "auth_expires_at",
                "permissions",
                "current_user",
                "demo_last_run",
            ):
                st.session_state.pop(key, None)
            st.rerun()

    pages = st.navigation(page_groups)
    pages.run()
    