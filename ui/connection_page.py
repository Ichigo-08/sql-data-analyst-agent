"""Streamlit database connection center."""
from __future__ import annotations

from pathlib import Path
import shutil
import re

import streamlit as st

from database.connection_manager import (
    ConnectionConfig,
    ConnectionManager,
    ConnectionConfigurationError,
    ProfileStore,
    test_connection,
)


def _manager() -> ConnectionManager:
    if "connection_manager" not in st.session_state:
        st.session_state.connection_manager = ConnectionManager()
    return st.session_state.connection_manager


def _profile_store() -> ProfileStore:
    return ProfileStore()


def _show_active_connection(manager: ConnectionManager) -> None:
    info = manager.connection_info()
    if info:
        st.success(f"Connected to {info['database']} ({info['database_type']})")
        st.caption(f"Endpoint: {info['endpoint']}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Reconnect", use_container_width=True):
                try:
                    result = manager.reconnect()
                    st.success(result["message"])
                    st.rerun()
                except Exception as exc:
                    st.error(f"Reconnect failed: {exc}")
        with c2:
            if st.button("Disconnect", use_container_width=True):
                manager.disconnect()
                st.success("Disconnected.")
                st.rerun()
    else:
        st.info("No database is currently connected.")


def _save_profile(config: ConnectionConfig, profile_name: str, save: bool) -> None:
    if save:
        try:
            _profile_store().save(profile_name, config)
            st.success("Profile saved. Passwords are not stored; re-enter them when reconnecting.")
        except Exception as exc:
            st.error(str(exc))


def render_connection_page() -> None:
    st.title("Database Connections")
    st.write("Connect a local SQLite file or a PostgreSQL/MySQL database.")
    manager = _manager()
    _show_active_connection(manager)

    st.divider()
    st.subheader("Saved connection profiles")
    profiles = _profile_store().list_profiles()
    loaded_profile = {}
    selected = "Select a profile"
    if profiles:
        selected = st.selectbox("Profile", ["Select a profile"] + list(profiles.keys()))
        if selected != "Select a profile":
            loaded_profile = profiles[selected]
            st.caption(
                f"{loaded_profile.get('database_type', '').upper()} · "
                f"{loaded_profile.get('database') or loaded_profile.get('sqlite_path', '')}"
            )
            load_col, delete_col = st.columns(2)
            with load_col:
                if st.button("Load profile details"):
                    st.session_state["loaded_connection_profile"] = loaded_profile
                    st.success("Profile details loaded. Enter the password again if required.")
                    st.rerun()
            with delete_col:
                if st.button("Delete selected profile"):
                    _profile_store().delete(selected)
                    st.rerun()
    else:
        st.caption("No saved profiles yet. Save a profile below; passwords are never persisted.")

    loaded_profile = st.session_state.get("loaded_connection_profile", loaded_profile)
    sqlite_tab, pg_tab, mysql_tab = st.tabs(["SQLite", "PostgreSQL", "MySQL"])

    with sqlite_tab:
        # Apply a newly-created database path BEFORE the text_input widget is instantiated.
        # Streamlit does not allow changing a widget's own session-state key after creation.
        pending_path = st.session_state.pop("pending_sqlite_path", None)
        if pending_path:
            st.session_state["sqlite_path"] = pending_path
        elif "sqlite_path" not in st.session_state:
            default_path = (
                loaded_profile.get("sqlite_path", "data/sample.db")
                if loaded_profile.get("database_type") == "sqlite" else "data/sample.db"
            )
            st.session_state["sqlite_path"] = default_path

        st.markdown("#### Connect an existing SQLite database")
        sqlite_path = st.text_input(
            "Database file path",
            help="Enter a path on this computer. You can also upload a .db or .sqlite file below.",
            key="sqlite_path",
        )
        uploaded = st.file_uploader("Or upload an existing SQLite database", type=["db", "sqlite", "sqlite3"])
        if uploaded is not None:
            safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(uploaded.name).name)
            target = Path("data/uploaded_databases") / safe_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(uploaded.getbuffer())
            sqlite_path = str(target)
            st.success(f"Database file staged at {target}")

        st.markdown("#### Create a new SQLite database")
        new_db_name = st.text_input("New database filename", value="new_database.db")
        if st.button("Create SQLite database", use_container_width=True):
            if not new_db_name.lower().endswith((".db", ".sqlite", ".sqlite3")):
                st.error("Use a .db, .sqlite or .sqlite3 filename.")
            else:
                target = Path("data") / Path(new_db_name).name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch(exist_ok=True)
                st.success(f"SQLite database created: {target}")
                # Queue the path for the next rerun; it will be applied before text_input exists.
                st.session_state["pending_sqlite_path"] = str(target)
                st.rerun()

        profile_name = st.text_input("Profile name (optional)", key="sqlite_profile")
        save_profile = st.checkbox("Save non-secret connection details", key="sqlite_save")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Test SQLite connection", use_container_width=True):
                try:
                    result = test_connection(ConnectionConfig("sqlite", sqlite_path=sqlite_path))
                    st.success(f"{result['message']} Dialect: {result['dialect']}")
                except Exception as exc:
                    st.error(f"Connection test failed: {exc}")
        with col2:
            if st.button("Connect SQLite", type="primary", use_container_width=True):
                try:
                    config = ConnectionConfig("sqlite", sqlite_path=sqlite_path)
                    result = manager.connect(config)
                    _save_profile(config, profile_name, save_profile)
                    st.success(result["message"])
                    st.rerun()
                except Exception as exc:
                    st.error(f"Connection failed: {exc}")

    with pg_tab:
        st.markdown("#### PostgreSQL connection")
        with st.form("postgres_connection"):
            host = st.text_input("Host", value=(loaded_profile.get("host", "") if loaded_profile.get("database_type") == "postgresql" else ""), placeholder="localhost")
            port = st.number_input("Port", min_value=1, max_value=65535, value=int(loaded_profile.get("port") or 5432) if loaded_profile.get("database_type") == "postgresql" else 5432)
            database = st.text_input("Database name", value=(loaded_profile.get("database", "") if loaded_profile.get("database_type") == "postgresql" else ""))
            username = st.text_input("Username", value=(loaded_profile.get("username", "") if loaded_profile.get("database_type") == "postgresql" else ""))
            password = st.text_input("Password", type="password")
            profile_name = st.text_input("Profile name (optional)")
            save_profile = st.checkbox("Save non-secret connection details")
            test_btn = st.form_submit_button("Test connection")
            connect_btn = st.form_submit_button("Connect", type="primary")
        if test_btn or connect_btn:
            config = ConnectionConfig(
                "postgresql", database=database, host=host, port=int(port),
                username=username, password=password
            )
            try:
                if test_btn:
                    result = test_connection(config)
                    st.success(f"{result['message']} PostgreSQL version: {result['server_version']}")
                else:
                    result = manager.connect(config)
                    _save_profile(config, profile_name, save_profile)
                    st.success(result["message"])
                    st.rerun()
            except Exception as exc:
                st.error(f"PostgreSQL connection failed: {exc}")

    with mysql_tab:
        st.markdown("#### MySQL connection")
        with st.form("mysql_connection"):
            host = st.text_input("Host", value=(loaded_profile.get("host", "") if loaded_profile.get("database_type") == "mysql" else ""), placeholder="localhost")
            port = st.number_input("Port", min_value=1, max_value=65535, value=int(loaded_profile.get("port") or 3306) if loaded_profile.get("database_type") == "mysql" else 3306)
            database = st.text_input("Database name", value=(loaded_profile.get("database", "") if loaded_profile.get("database_type") == "mysql" else ""))
            username = st.text_input("Username", value=(loaded_profile.get("username", "") if loaded_profile.get("database_type") == "mysql" else ""))
            password = st.text_input("Password", type="password")
            profile_name = st.text_input("Profile name (optional)")
            save_profile = st.checkbox("Save non-secret connection details")
            test_btn = st.form_submit_button("Test connection")
            connect_btn = st.form_submit_button("Connect", type="primary")
        if test_btn or connect_btn:
            config = ConnectionConfig(
                "mysql", database=database, host=host, port=int(port),
                username=username, password=password
            )
            try:
                if test_btn:
                    result = test_connection(config)
                    st.success(f"{result['message']} MySQL version: {result['server_version']}")
                else:
                    result = manager.connect(config)
                    _save_profile(config, profile_name, save_profile)
                    st.success(result["message"])
                    st.rerun()
            except Exception as exc:
                st.error(f"MySQL connection failed: {exc}")
