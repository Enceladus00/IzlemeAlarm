import os
from typing import Any

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = 20


class ApiError(Exception):
    pass


def api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
) -> Any:
    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{path}",
            params=params,
            json=json,
            files=files,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ApiError(f"API not reachable at {API_BASE_URL}: {exc}") from exc
    if not response.ok:
        try:
            message = response.json().get("detail", response.text)
        except ValueError:
            message = response.text
        raise ApiError(f"Request failed ({response.status_code}): {message}")
    if response.status_code == 204:
        return None
    return response.json()


def show_api_error(error: ApiError) -> None:
    st.error(str(error))
