import time

import pandas as pd
import streamlit as st

from components.common import page_header
from utils.api import ApiError, api_request, show_api_error


page_header(
    "System overview",
    "Operational health, data volume, and security configuration.",
)

if st.button("Refresh data", icon=":material/refresh:"):
    st.rerun()

try:
    request_started = time.perf_counter()
    overview = api_request("GET", "/admin/system-overview")
    api_latency_ms = round((time.perf_counter() - request_started) * 1000)

    health = overview["health"]
    rules = overview["rules"]
    security = overview["security"]
    cards = st.columns(4)
    with cards[0].container(border=True):
        st.markdown("**API**")
        st.success(f"Available · {api_latency_ms} ms")
        st.caption("GET /admin/system-overview")
    with cards[1].container(border=True):
        st.markdown("**Database**")
        st.success("Connected")
        st.caption(f"SELECT 1 · {health['database_latency_ms']} ms")
    with cards[2].container(border=True):
        st.markdown("**Schema version**")
        st.info(health["schema_revision"] or "Unknown")
        st.caption("Alembic revision")
    with cards[3].container(border=True):
        st.markdown("**Rule engine**")
        st.metric("Active rules", f"{rules['active']:,}")
        if rules["last_run_at"]:
            run_caption = f"Last run · {rules['last_run_at']}"
            if rules["last_run_duration_ms"] is not None:
                run_caption += f" · {rules['last_run_duration_ms']:,} ms"
            st.caption(run_caption)
        else:
            st.caption("No rule runs recorded")

    records = overview["records"]
    record_rows = [
        {
            "Table": label,
            "Total": records[key]["total"],
            "Last 7 days": records[key]["added_last_7_days"],
            "Last added": records[key]["last_added_at"] or "—",
        }
        for key, label in (
            ("customers", "Customers"),
            ("accounts", "Accounts"),
            ("transactions", "Transactions"),
            ("alerts", "Alerts"),
        )
    ]
    data_col, security_col = st.columns([1.4, 1])
    with data_col.container(border=True):
        st.subheader("Record volume")
        st.dataframe(
            pd.DataFrame(record_rows),
            hide_index=True,
            use_container_width=True,
            alt="Record totals, additions in the last seven days, and last-added timestamps",
        )
        st.caption(
            "Account creation history is available from the system-overview migration; "
            "older accounts may not have a recorded creation date."
        )

    with security_col.container(border=True):
        st.subheader("Security and configuration")
        st.metric(
            "Session duration",
            f"{security['session_ttl_seconds'] // 60} min",
        )
        st.metric(
            "Active users",
            f"{security['active_users']:,} / {security['total_users']:,}",
        )
        st.metric(
            "Demo data endpoint",
            "Enabled" if security["demo_endpoint_enabled"] else "Disabled",
        )
        st.metric(
            "CSV upload limits",
            f"{security['csv_max_bytes'] // (1024 * 1024)} MB · "
            f"{security['csv_max_rows']:,} rows",
        )
        st.markdown("**Security events · last 24 hours**")
        st.write(
            f"Failed logins: **{security['failed_logins_last_24h']:,}**  \n"
            f"Access denied: **{security['access_denied_last_24h']:,}**"
        )
except ApiError as error:
    show_api_error(error)
