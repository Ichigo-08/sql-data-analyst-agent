"""Streamlit Database Explorer page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from database.database_manager import DatabaseManager


def render_explorer_page() -> None:
    st.title("Database Explorer")
    st.caption("Inspect tables, columns, relationships and records in your connected database.")

    connection_manager = st.session_state.get("connection_manager")
    if not connection_manager or not connection_manager.connected or not connection_manager.engine:
        st.warning("No database is connected. Open Database Connections and connect a database first.")
        return

    manager = DatabaseManager(connection_manager.engine)
    try:
        tables = manager.tables()
    except Exception as exc:
        st.error(f"Could not inspect database schema: {exc}")
        return

    if not tables:
        st.info("This database does not contain any tables or views yet. Import a CSV/Excel file or create tables before exploring data.")
        st.metric("Tables and views", 0)
        return

    table_names = [item["name"] for item in tables]
    table_count = sum(item["type"] == "table" for item in tables)
    view_count = sum(item["type"] == "view" for item in tables)
    c1, c2, c3 = st.columns(3)
    c1.metric("Tables", table_count)
    c2.metric("Views", view_count)
    try:
        relationships = manager.relationships()
    except Exception:
        relationships = []
    c3.metric("Declared relationships", len(relationships))

    st.divider()
    selected = st.selectbox("Select a table or view", table_names)
    try:
        details = manager.table_details(selected)
        row_count = manager.row_count(selected)
    except Exception as exc:
        st.error(f"Could not inspect '{selected}': {exc}")
        return

    st.subheader(f"Table overview: {selected}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Rows", f"{row_count:,}")
    m2.metric("Columns", len(details["columns"]))
    m3.metric("Primary key columns", len(details["primary_key"]))

    tabs = st.tabs(["Data preview", "Columns & keys", "Relationships", "Statistics"])

    with tabs[0]:
        st.markdown("#### Browse records")
        col_a, col_b = st.columns([1, 2])
        with col_a:
            page_size = st.selectbox("Rows per page", [10, 25, 50, 100, 250, 500], index=2)
        with col_b:
            search_col_options = ["No search"] + [col["name"] for col in details["columns"]]
            search_column = st.selectbox("Search within column", search_col_options)
        search_text = st.text_input("Search value", placeholder="Enter text to find in the selected column")
        page_key = f"explorer_page_{selected}"
        if page_key not in st.session_state:
            st.session_state[page_key] = 1
        if st.button("Reset pagination"):
            st.session_state[page_key] = 1
        actual_search_col = None if search_column == "No search" else search_column
        try:
            data, total = manager.preview(
                selected, page=st.session_state[page_key], page_size=page_size,
                search_column=actual_search_col, search_text=search_text or None
            )
            total_pages = max(1, (total + page_size - 1) // page_size)
            if st.session_state[page_key] > total_pages:
                st.session_state[page_key] = total_pages
                data, total = manager.preview(
                    selected, page=total_pages, page_size=page_size,
                    search_column=actual_search_col, search_text=search_text or None
                )
            p1, p2, p3 = st.columns([1, 2, 1])
            with p1:
                if st.button("← Previous", disabled=st.session_state[page_key] <= 1):
                    st.session_state[page_key] -= 1
                    st.rerun()
            with p2:
                st.caption(f"Page {st.session_state[page_key]} of {total_pages} · {total:,} matching rows")
            with p3:
                if st.button("Next →", disabled=st.session_state[page_key] >= total_pages):
                    st.session_state[page_key] += 1
                    st.rerun()
            st.dataframe(data, use_container_width=True, hide_index=True)
            st.download_button(
                "Download current page as CSV",
                data=data.to_csv(index=False).encode("utf-8"),
                file_name=f"{selected}_page_{st.session_state[page_key]}.csv",
                mime="text/csv",
            )
        except Exception as exc:
            st.error(f"Could not load table preview: {exc}")

    with tabs[1]:
        st.markdown("#### Column definitions")
        st.dataframe(pd.DataFrame(details["columns"]), use_container_width=True, hide_index=True)
        st.markdown("#### Primary key")
        st.write(", ".join(details["primary_key"]) if details["primary_key"] else "No declared primary key.")
        st.markdown("#### Foreign keys")
        if details["foreign_keys"]:
            st.dataframe(pd.DataFrame(details["foreign_keys"]), use_container_width=True, hide_index=True)
        else:
            st.info("No declared foreign keys for this table.")
        if details["indexes"]:
            st.markdown("#### Indexes")
            st.dataframe(pd.DataFrame(details["indexes"]), use_container_width=True, hide_index=True)

    with tabs[2]:
        table_relationships = [
            rel for rel in relationships
            if rel["source_table"] == selected or rel["target_table"] == selected
        ]
        if table_relationships:
            st.dataframe(pd.DataFrame(table_relationships), use_container_width=True, hide_index=True)
        else:
            st.info("No declared foreign-key relationships involving this table.")
        with st.expander("All database relationships"):
            if relationships:
                st.dataframe(pd.DataFrame(relationships), use_container_width=True, hide_index=True)
            else:
                st.write("No declared foreign-key relationships found.")

    with tabs[3]:
        st.markdown("#### Column statistics")
        if not details["columns"]:
            st.info("No columns available.")
        else:
            selected_column = st.selectbox(
                "Choose a column for statistics",
                [col["name"] for col in details["columns"]],
                key=f"stats_column_{selected}",
            )
            if st.button("Calculate statistics"):
                try:
                    stats = manager.column_statistics(selected, selected_column)
                    st.json(stats)
                except Exception as exc:
                    st.error(f"Could not calculate statistics: {exc}")
