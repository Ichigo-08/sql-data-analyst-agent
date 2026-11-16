"""Interactive SQL workspace."""
from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from config.settings import settings
from sql_engine.sql_validator import validate_read_only_sql, SQLValidationError
from sql_engine.query_executor import execute_read_only_query, QueryExecutionError


DEFAULT_QUERY = """-- Write a read-only SELECT query below.
-- Example:
-- SELECT name FROM sqlite_master WHERE type = 'table';

SELECT 1 AS connection_test;
"""


def render_query_page() -> None:
    st.title("SQL Workspace")
    st.caption("Write, validate and execute read-only SQL against your active database.")

    manager = st.session_state.get("connection_manager")
    if not manager or not manager.connected or not manager.engine:
        st.warning("No database is connected. Open Database Connections and connect a database first.")
        return

    info = manager.connection_info()
    st.success(f"Connected to {info['database']} ({info['database_type']}). Read-only query mode is enabled.")

    query = st.text_area(
        "SQL query editor",
        value=st.session_state.get("sql_editor_query", DEFAULT_QUERY),
        height=230,
        key="sql_editor_query",
        help="Only one SELECT statement or read-only SELECT CTE is permitted.",
    )
    params_text = st.text_input(
        "Query parameters (JSON object, optional)",
        value="{}",
        help='Example: {"region": "South"} for SQL containing :region.',
    )

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        validate_clicked = st.button("Validate SQL", use_container_width=True)
    with c2:
        execute_clicked = st.button("Execute query", type="primary", use_container_width=True)
    with c3:
        if st.button("Clear editor", use_container_width=True):
            st.session_state["sql_editor_query"] = ""
            st.session_state.pop("last_query_result", None)
            st.rerun()

    if validate_clicked or execute_clicked:
        try:
            validation = validate_read_only_sql(
                query, manager.engine.dialect.name, settings.max_query_length
            )
            st.success(validation.message)
            with st.expander("Validated SQL"):
                st.code(validation.normalized_sql, language="sql")
        except Exception as exc:
            st.error(f"Validation failed: {exc}")
            if execute_clicked:
                st.stop()

    if execute_clicked:
        try:
            parameters = json.loads(params_text or "{}")
            if not isinstance(parameters, dict):
                raise ValueError("Parameters must be a JSON object.")
            result = execute_read_only_query(
                manager.engine,
                query,
                parameters=parameters,
                max_rows=settings.max_result_rows,
                timeout_seconds=settings.query_timeout_seconds,
                max_query_length=settings.max_query_length,
            )
            st.session_state["last_query_result"] = {
                "dataframe": result.dataframe,
                "rows_returned": result.rows_returned,
                "elapsed_seconds": result.elapsed_seconds,
                "truncated": result.truncated,
                "message": result.message,
            }
        except json.JSONDecodeError:
            st.error("Query parameters must be valid JSON.")
        except (SQLValidationError, QueryExecutionError, ValueError) as exc:
            st.error(str(exc))

    result = st.session_state.get("last_query_result")
    if result:
        st.divider()
        st.subheader("Query results")
        m1, m2, m3 = st.columns(3)
        m1.metric("Rows returned", f"{result['rows_returned']:,}")
        m2.metric("Execution time", f"{result['elapsed_seconds']:.4f} sec")
        m3.metric("Result limit reached", "Yes" if result["truncated"] else "No")
        if result["truncated"]:
            st.warning("The result exceeded the configured row limit. Only the first rows are displayed.")
        st.success(result["message"])
        dataframe = result["dataframe"]
        st.dataframe(dataframe, use_container_width=True, hide_index=True)
        csv_data = dataframe.to_csv(index=False).encode("utf-8")
        st.download_button("Export results as CSV", csv_data, "query_results.csv", "text/csv")
        try:
            from io import BytesIO
            buffer = BytesIO()
            dataframe.to_excel(buffer, index=False, engine="openpyxl")
            st.download_button(
                "Export results as Excel",
                buffer.getvalue(),
                "query_results.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as exc:
            st.caption(f"Excel export unavailable: {exc}")
