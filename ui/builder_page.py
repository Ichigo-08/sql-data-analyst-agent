"""Streamlit visual SQL query builder."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from database.schema_inspector import list_tables
from sql_engine.query_builder import (
    AGGREGATIONS, FILTER_OPERATORS, QueryBuilderError,
    generate_select_query, get_join_candidates, get_table_columns,
)
from sql_engine.query_executor import execute_read_only_query, QueryExecutionError
from sql_engine.sql_validator import SQLValidationError


def render_builder_page() -> None:
    st.title("Visual SQL Query Builder")
    st.caption("Build parameterized SELECT queries using database tables, columns, filters and joins.")

    manager = st.session_state.get("connection_manager")
    if not manager or not manager.connected or not manager.engine:
        st.warning("No database is connected. Open Database Connections and connect a database first.")
        return

    engine = manager.engine
    info = manager.connection_info()
    st.success(f"Connected to {info['database']} ({info['database_type']}). Generated queries use the Phase 4 read-only execution engine.")

    try:
        tables = list_tables(engine)
    except Exception as exc:
        st.error(f"Could not load database tables: {exc}")
        return
    table_names = [item["name"] for item in tables]
    if not table_names:
        st.info("No tables or views were found. Import a dataset or create tables, then return to the Visual Query Builder.")
        return

    st.subheader("1. Choose a table")
    base_table = st.selectbox("Base table", table_names, key="builder_base_table")
    base_columns = get_table_columns(engine, base_table)
    base_names = [item["name"] for item in base_columns]
    join_options = ["No join"] + [name for name in table_names if name != base_table]
    join_choice = st.selectbox("Join another table (optional)", join_options, key="builder_join_table")
    join_table = None if join_choice == "No join" else join_choice

    join_type = "INNER"
    base_join_column = None
    joined_column = None
    available_join_names: list[str] = []
    if join_table:
        joined_columns = get_table_columns(engine, join_table)
        available_join_names = [item["name"] for item in joined_columns]
        candidates = get_join_candidates(engine, base_table, join_table)
        st.subheader("2. Configure join")
        join_type = st.selectbox("Join type", ["INNER", "LEFT", "RIGHT"], key="builder_join_type")
        if candidates:
            labels = [
                f"{item['base_column']} = {item['join_column']} ({item['relationship']})"
                for item in candidates
            ]
            chosen = st.selectbox("Detected foreign-key relationship", range(len(candidates)),
                                  format_func=lambda idx: labels[idx], key="builder_fk_candidate")
            base_join_column = candidates[chosen]["base_column"]
            joined_column = candidates[chosen]["join_column"]
            st.caption("Relationship detected from declared database foreign keys.")
        else:
            left, right = st.columns(2)
            with left:
                base_join_column = st.selectbox("Base-table join column", base_names, key="builder_base_join_col")
            with right:
                joined_column = st.selectbox("Joined-table join column", available_join_names, key="builder_join_join_col")
            st.caption("No declared foreign key was found. Select matching columns carefully.")

    st.subheader("3. Select output columns")
    all_available_columns = (
        [f"{base_table}.{name}" for name in base_names]
        + ([f"{join_table}.{name}" for name in available_join_names] if join_table else [])
    )
    selected_columns = st.multiselect(
        "Columns to include",
        all_available_columns,
        default=st.session_state.get("builder_selected_columns", []) ,
        key="builder_selected_columns",
        help="Columns are shown as table.column. When an aggregation is selected, these become grouping dimensions.",
    )

    st.subheader("4. Add filters")
    if "builder_filter_count" not in st.session_state:
        st.session_state["builder_filter_count"] = 1
    filters = []
    for index in range(st.session_state["builder_filter_count"]):
        st.markdown(f"**Filter {index + 1}**")
        c1, c2, c3 = st.columns([1.2, 1, 1.4])
        with c1:
            filter_column = st.selectbox(
                "Column", all_available_columns, key=f"builder_filter_col_{index}"
            )
        with c2:
            filter_operator = st.selectbox(
                "Operator", FILTER_OPERATORS, key=f"builder_filter_op_{index}"
            )
        with c3:
            filter_value = st.text_input(
                "Value (IN accepts comma-separated values)",
                key=f"builder_filter_value_{index}",
                disabled=filter_operator in {"IS NULL", "IS NOT NULL"},
            )
        # Ignore untouched filter rows; only include explicit conditions.
        if filter_operator in {"IS NULL", "IS NOT NULL"} or filter_value.strip():
            filters.append({"column": filter_column, "operator": filter_operator, "value": filter_value})
    add_col, remove_col = st.columns(2)
    with add_col:
        if st.button("＋ Add filter", disabled=st.session_state["builder_filter_count"] >= 5):
            st.session_state["builder_filter_count"] += 1
            st.rerun()
    with remove_col:
        if st.button("－ Remove last filter", disabled=st.session_state["builder_filter_count"] <= 1):
            st.session_state["builder_filter_count"] -= 1
            st.rerun()

    st.subheader("5. Aggregation and grouping")
    agg_col, agg_func_col = st.columns(2)
    with agg_func_col:
        aggregation = st.selectbox("Aggregation", list(AGGREGATIONS.keys()), key="builder_aggregation")
    aggregation_column = None
    if aggregation != "None":
        aggregation_choices = ["*"] + all_available_columns if aggregation == "COUNT" else all_available_columns
        with agg_col:
            aggregation_column = st.selectbox("Column to aggregate", aggregation_choices, key="builder_agg_column")
    else:
        with agg_col:
            st.selectbox("Column to aggregate", ["Not applicable"], disabled=True)

    st.subheader("6. Sorting and result limit")
    sort_col, sort_dir, limit_col = st.columns([2, 1, 1])
    order_choices = list(selected_columns)
    if aggregation != "None":
        order_choices.append("aggregation_value")
    with sort_col:
        order_by = st.selectbox("Sort by (optional)", ["No sorting"] + order_choices, key="builder_order_by")
    with sort_dir:
        order_direction = st.selectbox("Direction", ["ASC", "DESC"], key="builder_order_direction")
    with limit_col:
        limit = st.number_input("Maximum rows", min_value=1, max_value=100000, value=1000, step=100)

    if st.button("Generate SQL", type="primary", use_container_width=True):
        try:
            generated_sql, parameters = generate_select_query(
                engine,
                base_table=base_table,
                selected_columns=selected_columns,
                aggregation=aggregation,
                aggregation_column=aggregation_column,
                join_table=join_table,
                join_type=join_type,
                base_join_column=base_join_column,
                joined_column=joined_column,
                filters=filters,
                order_by=None if order_by == "No sorting" else order_by,
                order_direction=order_direction,
                limit=int(limit),
            )
            st.session_state["builder_generated_sql"] = generated_sql
            st.session_state["builder_generated_params"] = parameters
            st.session_state.pop("builder_last_result", None)
        except QueryBuilderError as exc:
            st.error(str(exc))

    generated_sql = st.session_state.get("builder_generated_sql")
    if generated_sql:
        st.divider()
        st.subheader("7. Generated SQL")
        st.code(generated_sql, language="sql")
        params = st.session_state.get("builder_generated_params", {})
        with st.expander("Bound query parameters"):
            st.json(params)
        if st.button("Validate and execute generated SQL", type="primary", use_container_width=True):
            try:
                result = execute_read_only_query(
                    engine,
                    generated_sql,
                    parameters=params,
                )
                st.session_state["builder_last_result"] = {
                    "dataframe": result.dataframe,
                    "rows_returned": result.rows_returned,
                    "elapsed_seconds": result.elapsed_seconds,
                    "truncated": result.truncated,
                    "message": result.message,
                }
                st.success("Generated query executed successfully.")
            except (SQLValidationError, QueryExecutionError, ValueError) as exc:
                st.error(f"Query could not be executed: {exc}")

    result = st.session_state.get("builder_last_result")
    if result:
        st.divider()
        st.subheader("8. Query results")
        c1, c2, c3 = st.columns(3)
        c1.metric("Rows returned", f"{result['rows_returned']:,}")
        c2.metric("Execution time", f"{result['elapsed_seconds']:.4f} sec")
        c3.metric("Result limit reached", "Yes" if result["truncated"] else "No")
        st.dataframe(result["dataframe"], use_container_width=True, hide_index=True)
        dataframe = result["dataframe"]
        st.download_button(
            "Export CSV",
            dataframe.to_csv(index=False).encode("utf-8"),
            "visual_query_results.csv",
            "text/csv",
        )
        try:
            from io import BytesIO
            output = BytesIO()
            dataframe.to_excel(output, index=False, engine="openpyxl")
            st.download_button(
                "Export Excel",
                output.getvalue(),
                "visual_query_results.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as exc:
            st.caption(f"Excel export unavailable: {exc}")
