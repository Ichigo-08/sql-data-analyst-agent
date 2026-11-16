"""Database-agnostic, read-only analytics operations for the dashboard."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import MetaData, Table, and_, func, inspect, select
from sqlalchemy.engine import Engine

SUPPORTED_AGGREGATIONS = {
    "COUNT": func.count,
    "DISTINCT COUNT": func.count,
    "SUM": func.sum,
    "AVERAGE": func.avg,
    "MINIMUM": func.min,
    "MAXIMUM": func.max,
}


def get_dashboard_schema(engine: Engine) -> list[dict[str, Any]]:
    """Return table/view columns with portable SQLAlchemy type metadata."""
    inspector = inspect(engine)
    result: list[dict[str, Any]] = []
    names = [(name, "table") for name in inspector.get_table_names()]
    names += [(name, "view") for name in inspector.get_view_names()]
    for name, kind in sorted(set(names), key=lambda item: item[0].lower()):
        columns = []
        for column in inspector.get_columns(name):
            col_type = column["type"]
            type_name = col_type.__class__.__name__.lower()
            python_type = None
            try:
                python_type = col_type.python_type
            except (AttributeError, NotImplementedError):
                pass
            columns.append({
                "name": column["name"],
                "type": str(col_type),
                "type_name": type_name,
                "nullable": bool(column.get("nullable", True)),
                "numeric": python_type in {int, float} or any(
                    token in type_name for token in ("int", "numeric", "decimal", "float", "double", "real")
                ),
                "date": python_type in {date, datetime} or any(
                    token in type_name for token in ("date", "time")
                ) or any(token in column["name"].lower() for token in ("date", "timestamp", "_at")),
                "text": python_type is str or any(
                    token in type_name for token in ("char", "text", "string", "enum")
                ),
            })
        result.append({"name": name, "type": kind, "columns": columns})
    return result


def _reflect_table(engine: Engine, table_name: str) -> Table:
    available = {item["name"] for item in get_dashboard_schema(engine)}
    if table_name not in available:
        raise ValueError(f"Unknown table or view: {table_name}")
    return Table(table_name, MetaData(), autoload_with=engine)


def _build_filters(table: Table, filters: Iterable[dict[str, Any]] | None):
    clauses = []
    for index, item in enumerate(filters or []):
        column_name = item.get("column")
        operator = str(item.get("operator", "=")).upper()
        if column_name not in table.c:
            raise ValueError(f"Unknown filter column: {column_name}")
        column = table.c[column_name]
        value = item.get("value")
        if operator == "IS NULL":
            clauses.append(column.is_(None))
        elif operator == "IS NOT NULL":
            clauses.append(column.is_not(None))
        elif operator == "=":
            clauses.append(column == value)
        elif operator in {"!=", "<>", "NOT EQUAL"}:
            clauses.append(column != value)
        elif operator == ">":
            clauses.append(column > value)
        elif operator == ">=":
            clauses.append(column >= value)
        elif operator == "<":
            clauses.append(column < value)
        elif operator == "<=":
            clauses.append(column <= value)
        elif operator == "CONTAINS":
            clauses.append(column.cast(__import__('sqlalchemy').String).ilike(f"%{value}%"))
        elif operator == "IN":
            values = value if isinstance(value, (list, tuple, set)) else [v.strip() for v in str(value).split(",") if v.strip()]
            if not values:
                raise ValueError("IN filters require at least one value.")
            clauses.append(column.in_(list(values)))
        elif operator == "BETWEEN":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError("BETWEEN filters require two values.")
            clauses.append(column.between(value[0], value[1]))
        else:
            raise ValueError(f"Unsupported filter operator: {operator}")
    return clauses


def _dataframe(engine: Engine, statement, max_rows: int = 10000) -> pd.DataFrame:
    if not 1 <= int(max_rows) <= 100000:
        raise ValueError("Maximum rows must be between 1 and 100,000.")
    statement = statement.limit(int(max_rows))
    with engine.connect() as connection:
        result = connection.execute(statement)
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()))


def calculate_kpi(
    engine: Engine,
    table_name: str,
    column_name: str | None,
    aggregation: str,
    filters: Iterable[dict[str, Any]] | None = None,
) -> Any:
    """Calculate a single KPI using a SQL aggregate, not a full table download."""
    table = _reflect_table(engine, table_name)
    aggregation = aggregation.upper()
    if aggregation not in SUPPORTED_AGGREGATIONS:
        raise ValueError(f"Unsupported aggregation: {aggregation}")
    if aggregation == "COUNT" and (column_name in {None, "*"}):
        expression = func.count()
    else:
        if column_name not in table.c:
            raise ValueError("Select a valid column for this aggregation.")
        column = table.c[column_name]
        if aggregation == "DISTINCT COUNT":
            expression = func.count(column.distinct())
        else:
            expression = SUPPORTED_AGGREGATIONS[aggregation](column)
    statement = select(expression.label("value")).select_from(table)
    clauses = _build_filters(table, filters)
    if clauses:
        statement = statement.where(and_(*clauses))
    with engine.connect() as connection:
        return connection.execute(statement).scalar_one()


def fetch_chart_data(
    engine: Engine,
    table_name: str,
    x_column: str,
    y_column: str | None = None,
    aggregation: str = "None",
    filters: Iterable[dict[str, Any]] | None = None,
    group_by: str | None = None,
    max_rows: int = 10000,
) -> pd.DataFrame:
    """Fetch bounded chart data; aggregations are performed by the database."""
    table = _reflect_table(engine, table_name)
    if x_column not in table.c:
        raise ValueError("Select a valid X-axis column.")
    if y_column and y_column != "*" and y_column not in table.c:
        raise ValueError("Select a valid Y-axis column.")
    aggregation = aggregation.upper()
    if aggregation == "NONE":
        columns = [table.c[x_column]]
        if y_column and y_column != x_column:
            columns.append(table.c[y_column])
        statement = select(*columns).select_from(table)
    else:
        if aggregation not in SUPPORTED_AGGREGATIONS:
            raise ValueError(f"Unsupported aggregation: {aggregation}")
        if not y_column:
            raise ValueError("Select a Y-axis column for an aggregated chart.")
        y = table.c[y_column] if y_column != "*" else None
        aggregate = func.count() if aggregation == "COUNT" and y_column == "*" else (
            func.count(y.distinct()) if aggregation == "DISTINCT COUNT" else SUPPORTED_AGGREGATIONS[aggregation](y)
        )
        group_columns = [table.c[x_column]]
        if group_by and group_by != x_column:
            if group_by not in table.c:
                raise ValueError("Select a valid grouping column.")
            group_columns.append(table.c[group_by])
        statement = select(*group_columns, aggregate.label("value")).select_from(table).group_by(*group_columns)
        statement = statement.order_by(table.c[x_column])
    clauses = _build_filters(table, filters)
    if clauses:
        statement = statement.where(and_(*clauses))
    return _dataframe(engine, statement, max_rows=max_rows)


def fetch_table_preview(
    engine: Engine,
    table_name: str,
    filters: Iterable[dict[str, Any]] | None = None,
    max_rows: int = 200,
) -> pd.DataFrame:
    """Fetch a bounded, filtered preview containing all columns from a table/view."""
    table = _reflect_table(engine, table_name)
    statement = select(table)
    clauses = _build_filters(table, filters)
    if clauses:
        statement = statement.where(and_(*clauses))
    return _dataframe(engine, statement, max_rows=max_rows)


def fetch_distinct_values(engine: Engine, table_name: str, column_name: str, limit: int = 200) -> list[Any]:
    table = _reflect_table(engine, table_name)
    if column_name not in table.c:
        raise ValueError(f"Unknown column: {column_name}")
    statement = select(table.c[column_name]).where(table.c[column_name].is_not(None)).distinct().order_by(table.c[column_name]).limit(limit)
    with engine.connect() as connection:
        return list(connection.execute(statement).scalars())


def percentage_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100


def build_rule_based_insights(dataframe: pd.DataFrame, category_column: str, value_column: str) -> list[str]:
    """Create simple observations strictly from the supplied result data."""
    if dataframe.empty or category_column not in dataframe or value_column not in dataframe:
        return ["Not enough data is available to generate insights."]
    valid = dataframe[[category_column, value_column]].dropna()
    if valid.empty or not pd.api.types.is_numeric_dtype(valid[value_column]):
        return ["Not enough valid numeric data is available to generate insights."]
    grouped = valid.groupby(category_column, dropna=True)[value_column].sum().sort_values(ascending=False)
    if grouped.empty:
        return ["Not enough data is available to generate insights."]
    insights = [f"Highest value: {grouped.index[0]} ({grouped.iloc[0]:,.2f})."]
    if len(grouped) > 1:
        insights.append(f"Lowest value: {grouped.index[-1]} ({grouped.iloc[-1]:,.2f}).")
    return insights


def dataframe_to_excel(dataframe: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    dataframe.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def aggregate_time_series(
    dataframe: pd.DataFrame, date_column: str, value_column: str, granularity: str
) -> pd.DataFrame:
    """Aggregate bounded chart results into daily/weekly/monthly/quarterly/yearly buckets."""
    frequencies = {
        "Daily": "D", "Weekly": "W", "Monthly": "MS",
        "Quarterly": "QS", "Yearly": "YS",
    }
    if granularity not in frequencies:
        raise ValueError("Unsupported time-series granularity.")
    if date_column not in dataframe or value_column not in dataframe:
        raise ValueError("The selected date or value column is not available.")
    working = dataframe[[date_column, value_column]].copy()
    working[date_column] = pd.to_datetime(working[date_column], errors="coerce")
    working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    working = working.dropna(subset=[date_column, value_column]).set_index(date_column)
    if working.empty:
        return pd.DataFrame(columns=[date_column, value_column])
    result = working[value_column].resample(frequencies[granularity]).sum().reset_index()
    return result
