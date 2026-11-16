
"""Main Streamlit entry point for SQL Data Analyst."""

import streamlit as st

from config.settings import settings
from ui.connection_page import render_connection_page
from ui.explorer_page import render_explorer_page
from ui.query_page import render_query_page
from ui.builder_page import render_builder_page
from ui.dashboard_page import render_dashboard_page
from ui.import_page import render_import_page
from ui.ai_assistant_page import render_ai_assistant_page

st.set_page_config(
    page_title=settings.app_name,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1450px;}
    [data-testid="stMetric"] {background: var(--secondary-background-color);
        padding: 16px; border-radius: 12px; border: 1px solid rgba(128,128,128,.18);}
    div.stButton > button {border-radius: 8px; min-height: 2.5rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.title("SQL Data Analyst")
    st.caption("AI-powered analytics workspace")

    page = st.radio(
        "Navigation",
        [
            "Home",
            "Database Connections",
            "Database Explorer",
            "SQL Workspace",
            "Visual Query Builder",
            "Analytics Dashboard",
            "Import CSV / Excel",
            "AI SQL Assistant",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Phase 9 · Gemini AI integration")

if page == "Home":

    st.title("SQL Data Analyst")
    st.subheader("Your database analytics workspace")

    st.write(
        "Connect a database to explore its schema, inspect records, generate SQL, "
        "build visual queries, create interactive analytics dashboards, "
        "and use AI-powered natural language SQL generation."
    )

    connection_manager = st.session_state.get("connection_manager")
    connected = bool(connection_manager and connection_manager.connected)

    c1, c2, c3 = st.columns(3)

    c1.metric("Supported databases", "3")
    c2.metric("AI assistant", "Gemini enabled")
    c3.metric(
        "Connection status",
        "Connected" if connected else "Not connected",
    )

    if connected:
        info = connection_manager.connection_info()
        st.success(
            f"Active database: {info['database']} "
            f"({info['database_type']})"
        )
    else:
        st.info("Start by opening Database Connections in the sidebar.")

elif page == "Database Connections":
    render_connection_page()

elif page == "Database Explorer":
    render_explorer_page()

elif page == "SQL Workspace":
    render_query_page()

elif page == "Visual Query Builder":
    render_builder_page()

elif page == "Analytics Dashboard":
    render_dashboard_page()

elif page == "Import CSV / Excel":
    render_import_page()

elif page == "AI SQL Assistant":
    render_ai_assistant_page()
