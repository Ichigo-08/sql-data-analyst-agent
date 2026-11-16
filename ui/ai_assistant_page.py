
"""Gemini-powered AI SQL Assistant."""

import streamlit as st

from ai.ai_query_service import (
    generate_and_validate,
    execute_approved_ai_query,
)
from sql_engine.sql_validator import validate_read_only_sql, SQLValidationError


def render_ai_assistant_page():

    st.title("AI SQL Assistant")
    st.caption(
        "Ask questions about your database in plain English "
        "and generate read-only SQL using Gemini."
    )

    manager = st.session_state.get("connection_manager")

    if not manager or not manager.connected or not manager.engine:
        st.warning(
            "No database is connected. "
            "Open Database Connections and connect first."
        )
        return

    info = manager.connection_info()

    st.success(
        f"Connected to {info['database']} "
        f"({info['database_type']})"
    )

    st.subheader("Ask your database")

    question = st.text_area(
        "Enter your question",
        placeholder="Example: Show the top 10 customers by total spending",
        height=110,
        key="ai_sql_question",
    )

    if st.button(
        "Generate SQL with Gemini",
        type="primary",
        use_container_width=True,
    ):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            try:
                with st.spinner("Gemini is generating SQL..."):
                    result = generate_and_validate(
                        manager.engine,
                        question.strip(),
                    )

                st.session_state["ai_generated_sql"] = result["sql"]
                st.session_state["ai_sql_editor"] = result["sql"]
                st.session_state["ai_generated_question"] = question
                st.session_state.pop("ai_validated_sql", None)
                st.session_state.pop("ai_validated_editor_sql", None)
                st.session_state.pop("ai_query_result", None)

                st.rerun()

            except Exception as exc:
                st.error(f"SQL generation failed: {exc}")

    generated_sql = st.session_state.get("ai_generated_sql")

    if generated_sql:

        st.divider()
        st.subheader("Generated SQL")

        edited_sql = st.text_area(
            "Review or edit the SQL before execution",
            height=220,
            key="ai_sql_editor",
        )

        if st.button("Validate SQL", use_container_width=True):

            try:
                validation = validate_read_only_sql(
                    edited_sql,
                    manager.engine.dialect.name,
                )

                st.session_state["ai_validated_sql"] = (
                    validation.normalized_sql
                )
                st.session_state["ai_validated_editor_sql"] = edited_sql
                st.session_state.pop("ai_query_result", None)

                st.success("SQL passed read-only validation.")

            except (SQLValidationError, ValueError) as exc:
                st.session_state.pop("ai_validated_sql", None)
                st.session_state.pop("ai_validated_editor_sql", None)
                st.error(f"SQL validation failed: {exc}")

            except Exception as exc:
                st.session_state.pop("ai_validated_sql", None)
                st.session_state.pop("ai_validated_editor_sql", None)
                st.error(f"Validation error: {exc}")

        validated_sql = st.session_state.get("ai_validated_sql")
        validated_editor_sql = st.session_state.get(
            "ai_validated_editor_sql"
        )

        is_approved = (
            validated_sql is not None
            and validated_editor_sql == edited_sql
        )

        if not is_approved:
            st.info(
                "Review your SQL and click Validate SQL. "
                "Any edits require validation again."
            )

        if st.button(
            "Execute approved SQL",
            type="primary",
            disabled=not is_approved,
            use_container_width=True,
        ):
            try:
                with st.spinner("Executing read-only query..."):
                    result = execute_approved_ai_query(
                        manager.engine,
                        validated_sql,
                    )

                st.session_state["ai_query_result"] = result

            except Exception as exc:
                st.error(f"Query execution failed: {exc}")

    query_result = st.session_state.get("ai_query_result")

    if query_result is not None:

        st.divider()
        st.subheader("Query Results")

        col1, col2, col3 = st.columns(3)

        col1.metric("Rows returned", query_result.rows_returned)
        col2.metric(
            "Execution time",
            f"{query_result.elapsed_seconds:.4f} sec",
        )
        col3.metric(
            "Result limit reached",
            "Yes" if query_result.truncated else "No",
        )

        st.success(query_result.message)

        dataframe = query_result.dataframe

        st.dataframe(
            dataframe,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download results as CSV",
            dataframe.to_csv(index=False).encode("utf-8"),
            file_name="ai_query_results.csv",
            mime="text/csv",
        )
