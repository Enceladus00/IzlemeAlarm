import os
from typing import Any

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = 20


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
) -> Any:
    headers: dict[str, str] = {}
    token = st.session_state.get("auth_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{path}",
            params=params,
            json=json,
            data=data,
            files=files,
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ApiError(f"API not reachable at {API_BASE_URL}: {exc}") from exc
    if not response.ok:
        if response.status_code == 401 and path != "/auth/login":
            for key in ("auth_token", "permissions", "current_user"):
                st.session_state.pop(key, None)
            st.rerun()
        try:
            message = response.json().get("detail", response.text)
        except ValueError:
            message = response.text
        raise ApiError(
            f"Request failed ({response.status_code}): {message}",
            response.status_code,
        )
    if response.status_code == 204:
        return None
    return response.json()


def show_api_error(error: ApiError) -> None:
    if error.status_code == 403:
        st.error("You do not have permission to perform this action.")
    else:
        st.error(str(error))
