"""Streamlit page for importing CSV and Excel files into the connected database."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from database.data_importer import (
    DataImportError,
    get_excel_sheet_names,
    import_dataframe,
    read_uploaded_dataframe,
    validate_table_name,
)


def render_import_page() -> None:
    st.title("Import CSV / Excel Data")
    st.caption("Load local CSV or Excel files into your connected database.")
    manager = st.session_state.get("connection_manager")
    if not manager or not manager.connected or not manager.engine:
        st.warning("No database is connected. Open Database Connections and connect a database first.")
        return

    info = manager.connection_info()
    st.success(f"Connected to {info['database']} ({info['database_type']}).")
    st.info("Imports create or append tables in the connected database. Replacing a table requires explicit confirmation.")

    uploaded = st.file_uploader(
        "Choose a CSV or Excel file",
        # Do not rely on browser MIME detection: some browsers report CSV as
        # text/csv and Streamlit's front-end MIME filter may reject it.
        # The importer below validates the filename extension and file content.
        type=None,
        help="Accepted formats: .csv and .xlsx. Maximum file size: 50 MB; maximum import size: 250,000 rows.",
        key="data_import_upload",
    )
    if uploaded is None:
        st.caption("Supported formats: .csv and .xlsx")
        return

    file_bytes = uploaded.getvalue()
    try:
        sheet_names = get_excel_sheet_names(uploaded.name, file_bytes)
        selected_sheet = st.selectbox("Worksheet", sheet_names, key="data_import_sheet") if sheet_names else 0
        frame = read_uploaded_dataframe(uploaded.name, file_bytes, sheet_name=selected_sheet)
    except DataImportError as exc:
        st.error(str(exc))
        return

    st.subheader("Preview")
    left, right, third = st.columns(3)
    left.metric("Rows", f"{len(frame):,}")
    right.metric("Columns", f"{len(frame.columns):,}")
    third.metric("File size", f"{len(file_bytes) / (1024 * 1024):.2f} MB")
    st.dataframe(frame.head(100), use_container_width=True, hide_index=True)
    st.caption("Preview shows up to the first 100 rows. The import uses all validated rows.")

    st.divider()
    st.subheader("Import settings")
    default_table = Path(uploaded.name).stem.lower().replace(" ", "_")
    default_table = "".join(char for char in default_table if char.isalnum() or char == "_")
    if not default_table or not default_table[0].isalpha():
        default_table = f"imported_{default_table}" if default_table else "imported_data"
    table_name = st.text_input("Destination table name", value=default_table, key="data_import_table")
    mode = st.radio(
        "If the table already exists",
        ["Fail (safest)", "Append rows", "Replace table"],
        horizontal=True,
        key="data_import_mode",
    )
    replace_confirmed = False
    if mode == "Replace table":
        replace_confirmed = st.checkbox(
            "I understand that replacing an existing table deletes its current contents.",
            key="data_import_confirm_replace",
        )
    st.caption("Append is allowed only when uploaded column names match the existing table columns.")

    if st.button("Import data into database", type="primary", key="data_import_submit"):
        try:
            validate_table_name(table_name)
            mode_value = {"Fail (safest)": "fail", "Append rows": "append", "Replace table": "replace"}[mode]
            result = import_dataframe(
                manager.engine,
                frame,
                table_name,
                if_exists=mode_value,
                confirm_replace=replace_confirmed,
            )
            st.session_state["last_import_result"] = result
            st.success(
                f"Imported {result['imported_rows']:,} rows into '{result['table_name']}'. "
                f"The table now contains {result['total_rows']:,} rows."
            )
            st.info("Open Database Explorer or Analytics Dashboard to use the imported table.")
        except DataImportError as exc:
            st.error(str(exc))

    previous = st.session_state.get("last_import_result")
    if previous:
        with st.expander("Last successful import"):
            st.json(previous)
