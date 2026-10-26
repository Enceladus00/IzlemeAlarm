import pandas as pd
import streamlit as st

from components.common import page_header
from utils.api import ApiError, api_request, show_api_error


page_header(
    "User management",
    "Create user accounts, assign active roles, and deactivate access when needed.",
)

try:
    users = api_request("GET", "/users")
    roles = api_request("GET", "/users/roles")
    role_codes = [role["role_code"] for role in roles]

    with st.expander("Create user"):
        with st.form("create-user"):
            username = st.text_input("Username")
            password = st.text_input("Initial password", type="password")
            role_code = st.selectbox("Role", role_codes)
            if st.form_submit_button("Create user", type="primary"):
                try:
                    api_request(
                        "POST",
                        "/users",
                        json={
                            "username": username,
                            "password": password,
                            "role_code": role_code,
                        },
                    )
                    st.success("User created.")
                    st.rerun()
                except ApiError as error:
                    show_api_error(error)

    if users:
        st.dataframe(pd.DataFrame(users), hide_index=True, alt="Application users")
        selected_id = st.selectbox(
            "User to update",
            [user["user_id"] for user in users],
            format_func=lambda user_id: next(
                f"{user['username']} · {user['role_code']} · "
                f"{'active' if user['is_active'] else 'inactive'}"
                for user in users
                if user["user_id"] == user_id
            ),
        )
        selected = next(user for user in users if user["user_id"] == selected_id)
        with st.form(f"update-user-{selected_id}"):
            new_role = st.selectbox(
                "Role",
                role_codes,
                index=role_codes.index(selected["role_code"]),
            )
            active = st.checkbox("Account active", value=selected["is_active"])
            if st.form_submit_button("Save user"):
                try:
                    api_request(
                        "PATCH",
                        f"/users/{selected_id}",
                        json={"role_code": new_role, "is_active": active},
                    )
                    st.success("User updated.")
                    st.rerun()
                except ApiError as error:
                    show_api_error(error)
    else:
        st.info("No users are configured.")
except ApiError as error:
    show_api_error(error)
