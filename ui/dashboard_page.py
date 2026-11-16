"""Interactive, schema-driven analytics dashboard."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.dashboard_service import (
    aggregate_time_series,
    build_rule_based_insights,
    calculate_kpi,
    dataframe_to_excel,
    fetch_chart_data,
    fetch_distinct_values,
    fetch_table_preview,
    get_dashboard_schema,
)

FILTER_OPERATORS = ["=", "!=", ">", ">=", "<", "<=", "CONTAINS", "IN", "BETWEEN", "IS NULL", "IS NOT NULL"]
CHART_TYPES = ["Bar", "Line", "Area", "Pie", "Scatter", "Histogram"]
AGGREGATIONS = ["None", "COUNT", "DISTINCT COUNT", "SUM", "AVERAGE", "MINIMUM", "MAXIMUM"]


def _render_filters(engine, table_name: str, columns: list[dict]) -> list[dict]:
    st.subheader("Dashboard filters")
    filterable = [c for c in columns]
    if not filterable:
        return []
    enabled = st.checkbox("Enable a dashboard filter", key=f"dash_filter_enabled_{table_name}")
    if not enabled:
        return []
    names = [c["name"] for c in filterable]
    chosen = st.selectbox("Filter column", names, key=f"dash_filter_col_{table_name}")
    meta = next(c for c in columns if c["name"] == chosen)
    if meta["text"]:
        values = fetch_distinct_values(engine, table_name, chosen)
        if values:
            selected = st.multiselect("Values to include", values, key=f"dash_filter_values_{table_name}_{chosen}")
            return [{"column": chosen, "operator": "IN", "value": selected}] if selected else []
        text_value = st.text_input("Contains", key=f"dash_filter_text_{table_name}_{chosen}")
        return [{"column": chosen, "operator": "CONTAINS", "value": text_value}] if text_value else []
    if meta["date"]:
        start, end = st.date_input("Date range", value=(date(2024, 1, 1), date.today()), key=f"dash_filter_dates_{table_name}_{chosen}")
        return [{"column": chosen, "operator": "BETWEEN", "value": [start.isoformat(), end.isoformat()]}]
    if meta["numeric"]:
        min_value = st.number_input("Minimum value", value=0.0, key=f"dash_filter_min_{table_name}_{chosen}")
        max_value = st.number_input("Maximum value", value=1000000.0, key=f"dash_filter_max_{table_name}_{chosen}")
        return [{"column": chosen, "operator": "BETWEEN", "value": [min_value, max_value]}]
    return []


def render_dashboard_page() -> None:
    st.title("Analytics Dashboard")
    st.caption("Build interactive, database-independent dashboards without writing SQL.")
    manager = st.session_state.get("connection_manager")
    if not manager or not manager.connected or not manager.engine:
        st.warning("No database is connected. Open Database Connections and connect a database first.")
        return
    engine = manager.engine
    info = manager.connection_info()
    st.success(f"Connected to {info['database']} ({info['database_type']}). Dashboard queries are read-only.")
    try:
        schema = get_dashboard_schema(engine)
    except Exception as exc:
        st.error(f"Could not inspect database schema: {exc}")
        return
    if not schema:
        st.info("No tables or views are available in this database.")
        return

    table_names = [item["name"] for item in schema]
    table_name = st.selectbox("Choose data source", table_names, key="dashboard_table")
    table_meta = next(item for item in schema if item["name"] == table_name)
    columns = table_meta["columns"]
    if not columns:
        st.warning("The selected table has no inspectable columns.")
        return
    filters = _render_filters(engine, table_name, columns)

    st.divider()
    st.subheader("KPI cards")
    numeric_columns = [c["name"] for c in columns if c["numeric"]]
    all_columns = [c["name"] for c in columns]
    if "dashboard_kpis" not in st.session_state:
        st.session_state.dashboard_kpis = []
    with st.expander("Add a KPI", expanded=not st.session_state.dashboard_kpis):
        kpi_title = st.text_input("KPI title", value="Total records", key="dashboard_new_kpi_title")
        kpi_aggregation = st.selectbox("Aggregation", AGGREGATIONS[1:], key="dashboard_new_kpi_aggregation")
        kpi_choices = (["*"] if kpi_aggregation == "COUNT" else []) + (numeric_columns if kpi_aggregation in {"SUM", "AVERAGE", "MINIMUM", "MAXIMUM"} else all_columns)
        if kpi_aggregation == "COUNT":
            kpi_choices = ["*"] + all_columns
        if kpi_choices:
            kpi_column = st.selectbox("Column", kpi_choices, key="dashboard_new_kpi_column")
            if st.button("Add KPI card", key="dashboard_add_kpi"):
                st.session_state.dashboard_kpis.append({"table": table_name, "title": kpi_title.strip() or kpi_aggregation.title(), "aggregation": kpi_aggregation, "column": kpi_column})
                st.rerun()
        else:
            st.info("This table has no compatible columns for the selected aggregation.")
    active_kpis = [item for item in st.session_state.dashboard_kpis if item.get("table") == table_name]
    if active_kpis:
        cols = st.columns(min(4, len(active_kpis)))
        for index, kpi in enumerate(active_kpis):
            try:
                value = calculate_kpi(engine, table_name, kpi["column"], kpi["aggregation"], filters)
                display = f"{value:,.2f}" if isinstance(value, (int, float)) and value is not None else str(value)
                cols[index % len(cols)].metric(kpi["title"], display)
            except Exception as exc:
                cols[index % len(cols)].warning(f"{kpi['title']}: {exc}")
        remove_kpi = st.selectbox("Remove a KPI", ["None"] + [f"{i + 1}. {item['title']}" for i, item in enumerate(active_kpis)], key=f"dashboard_remove_kpi_{table_name}")
        if st.button("Remove selected KPI", key=f"dashboard_remove_kpi_button_{table_name}", disabled=remove_kpi == "None"):
            remove_index = int(remove_kpi.split(".", 1)[0]) - 1
            target = active_kpis[remove_index]
            st.session_state.dashboard_kpis.remove(target)
            st.rerun()
    else:
        st.caption("No KPI cards yet. Add one above to start building your dashboard.")

    st.divider()
    st.subheader("Interactive chart builder")
    with st.container(border=True):
        chart_title = st.text_input("Chart title", "Data overview", key="dashboard_chart_title")
        chart_type = st.selectbox("Chart type", CHART_TYPES, key="dashboard_chart_type")
        x_column = st.selectbox("X-axis / category", all_columns, key="dashboard_x_column")
        y_choices = ["(Record count)"] + all_columns
        y_selection = st.selectbox("Y-axis / value", y_choices, key="dashboard_y_column")
        aggregation = st.selectbox("Aggregation", AGGREGATIONS, key="dashboard_chart_aggregation")
        group_by = st.selectbox("Additional grouping (optional)", ["None"] + all_columns, key="dashboard_group_by")
        x_is_date = next((item["date"] for item in columns if item["name"] == x_column), False)
        granularity = st.selectbox("Time-series granularity", ["Daily", "Weekly", "Monthly", "Quarterly", "Yearly"], key="dashboard_time_granularity") if x_is_date else "None"
        make_chart = st.button("Generate chart", type="primary", key="dashboard_generate_chart")
    if make_chart:
        try:
            y_column = None if y_selection == "(Record count)" else y_selection
            if aggregation == "None" and chart_type not in {"Histogram", "Pie"} and y_column is None:
                st.error("Select a Y-axis column or choose an aggregation such as COUNT.")
            elif aggregation != "None" and y_column is None and aggregation != "COUNT":
                st.error("Select a Y-axis column for this aggregation.")
            else:
                result = fetch_chart_data(
                    engine, table_name, x_column,
                    y_column if y_column else ("*" if aggregation == "COUNT" else None),
                    aggregation, filters,
                    None if group_by == "None" else group_by,
                )
                result_y = "value" if aggregation != "None" else y_column
                if granularity != "None" and result_y and result_y in result.columns:
                    result = aggregate_time_series(result, x_column, result_y, granularity)
                st.session_state.dashboard_chart_result = {
                    "data": result, "title": chart_title, "type": chart_type,
                    "x": x_column, "y": result_y,
                    "color": None if group_by == "None" or group_by not in result.columns else group_by,
                    "granularity": granularity,
                }
        except Exception as exc:
            st.error(f"Could not generate chart: {exc}")
    chart_result = st.session_state.get("dashboard_chart_result")
    if chart_result:
        data = chart_result["data"]
        chart_kind = chart_result["type"]
        x = chart_result["x"]
        y = chart_result["y"]
        try:
            if data.empty:
                st.info("No records match the current filters.")
            elif chart_kind == "Bar":
                fig = px.bar(data, x=x, y=y, title=chart_result["title"])
            elif chart_kind == "Line":
                fig = px.line(data, x=x, y=y, title=chart_result["title"], markers=True)
            elif chart_kind == "Area":
                fig = px.area(data, x=x, y=y, title=chart_result["title"])
            elif chart_kind == "Pie":
                fig = px.pie(data, names=x, values=y if y in data.columns else None, title=chart_result["title"])
            elif chart_kind == "Scatter":
                fig = px.scatter(data, x=x, y=y, title=chart_result["title"])
            else:
                fig = px.histogram(data, x=x, title=chart_result["title"])
            fig.update_layout(legend_title_text="Series", margin=dict(l=20, r=20, t=60, b=20))
            st.plotly_chart(fig, use_container_width=True)
            st.subheader("Data behind this chart")
            st.dataframe(data, use_container_width=True, hide_index=True)
            left, right = st.columns(2)
            left.download_button("Download chart data (CSV)", data.to_csv(index=False).encode("utf-8"), "dashboard_chart.csv", "text/csv")
            right.download_button("Download chart data (Excel)", dataframe_to_excel(data), "dashboard_chart.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            if y and y in data.columns:
                insights = build_rule_based_insights(data, x, y)
                with st.expander("Data-supported insights"):
                    for insight in insights:
                        st.write(f"• {insight}")
            if st.button("＋ Add this chart to dashboard", key="dashboard_save_chart"):
                saved = st.session_state.setdefault("dashboard_saved_charts", [])
                saved.append({"data": data.copy(), "title": chart_result["title"], "type": chart_kind, "x": x, "y": y})
                st.success("Chart added to this dashboard session.")
        except Exception as exc:
            st.error(f"Chart rendering failed: {exc}")

    saved_charts = st.session_state.get("dashboard_saved_charts", [])
    if saved_charts:
        st.divider()
        st.subheader("Saved dashboard charts")
        for index, saved_chart in enumerate(saved_charts):
            with st.container(border=True):
                st.markdown(f"**{saved_chart['title']}**")
                saved_data = saved_chart["data"]
                saved_type = saved_chart["type"]
                saved_x, saved_y = saved_chart["x"], saved_chart["y"]
                if saved_data.empty:
                    st.info("No data available for this saved chart.")
                elif saved_type == "Bar":
                    saved_fig = px.bar(saved_data, x=saved_x, y=saved_y, title=saved_chart["title"])
                elif saved_type == "Line":
                    saved_fig = px.line(saved_data, x=saved_x, y=saved_y, title=saved_chart["title"], markers=True)
                elif saved_type == "Area":
                    saved_fig = px.area(saved_data, x=saved_x, y=saved_y, title=saved_chart["title"])
                elif saved_type == "Pie":
                    saved_fig = px.pie(saved_data, names=saved_x, values=saved_y if saved_y in saved_data.columns else None, title=saved_chart["title"])
                elif saved_type == "Scatter":
                    saved_fig = px.scatter(saved_data, x=saved_x, y=saved_y, title=saved_chart["title"])
                else:
                    saved_fig = px.histogram(saved_data, x=saved_x, title=saved_chart["title"])
                st.plotly_chart(saved_fig, use_container_width=True, key=f"saved_dashboard_chart_{index}")
                if st.button("Remove chart", key=f"remove_saved_dashboard_chart_{index}"):
                    saved_charts.pop(index)
                    st.rerun()

    st.divider()
    st.subheader("Data preview")
    preview = fetch_table_preview(engine, table_name, filters=filters, max_rows=200)
    st.dataframe(preview, use_container_width=True, hide_index=True)
    st.download_button("Export preview as CSV", preview.to_csv(index=False).encode("utf-8"), "dashboard_preview.csv", "text/csv")
    st.download_button("Export preview as Excel", dataframe_to_excel(preview), "dashboard_preview.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if st.button("Refresh dashboard", key="dashboard_refresh"):
        st.rerun()
