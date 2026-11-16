from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from analytics.dashboard_service import (
    aggregate_time_series,
    build_rule_based_insights,
    calculate_kpi,
    dataframe_to_excel,
    fetch_chart_data,
    fetch_distinct_values,
    fetch_table_preview,
    get_dashboard_schema,
    percentage_change,
)


@pytest.fixture
def engine(tmp_path):
    db = tmp_path / "dashboard_test.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                category TEXT,
                amount REAL,
                order_date TEXT,
                region TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO orders (order_id, category, amount, order_date, region) VALUES
            (1, 'Books', 100, '2026-01-01', 'South'),
            (2, 'Books', 150, '2026-01-02', 'South'),
            (3, 'Games', 300, '2026-02-01', 'West'),
            (4, 'Games', 50, '2026-02-02', 'West'),
            (5, 'Other', NULL, '2026-02-03', 'North')
        """))
    yield engine
    engine.dispose()


def test_schema_is_dynamic_and_identifies_types(engine):
    schema = get_dashboard_schema(engine)
    orders = next(item for item in schema if item["name"] == "orders")
    assert {column["name"] for column in orders["columns"]} == {
        "order_id", "category", "amount", "order_date", "region"
    }
    assert next(c for c in orders["columns"] if c["name"] == "amount")["numeric"]
    assert next(c for c in orders["columns"] if c["name"] == "category")["text"]


def test_kpi_aggregations(engine):
    assert calculate_kpi(engine, "orders", "*", "COUNT") == 5
    assert calculate_kpi(engine, "orders", "category", "DISTINCT COUNT") == 3
    assert calculate_kpi(engine, "orders", "amount", "SUM") == 600
    assert calculate_kpi(engine, "orders", "amount", "AVERAGE") == 150
    assert calculate_kpi(engine, "orders", "amount", "MINIMUM") == 50
    assert calculate_kpi(engine, "orders", "amount", "MAXIMUM") == 300


def test_kpi_parameterized_filters(engine):
    assert calculate_kpi(
        engine, "orders", "amount", "SUM",
        [{"column": "region", "operator": "=", "value": "South"}],
    ) == 250


def test_chart_data_aggregation_and_count_star(engine):
    result = fetch_chart_data(engine, "orders", "category", "amount", "SUM")
    assert list(result.columns) == ["category", "value"]
    grouped = result.set_index("category")["value"]
    assert grouped["Books"] == 250.0 and grouped["Games"] == 350.0
    assert pd.isna(grouped["Other"])
    counts = fetch_chart_data(engine, "orders", "region", "*", "COUNT")
    assert counts["value"].sum() == 5


def test_chart_data_filters_and_limit(engine):
    result = fetch_chart_data(
        engine, "orders", "category", "amount", "SUM",
        [{"column": "amount", "operator": ">", "value": 100}], max_rows=1,
    )
    assert len(result) == 1
    assert result.iloc[0]["value"] == 150


def test_invalid_table_column_and_filter_are_rejected(engine):
    with pytest.raises(ValueError):
        calculate_kpi(engine, "missing", "amount", "SUM")
    with pytest.raises(ValueError):
        calculate_kpi(engine, "orders", "not_a_column", "SUM")
    with pytest.raises(ValueError):
        fetch_chart_data(engine, "orders", "category", "amount", "SUM", [
            {"column": "unknown", "operator": "=", "value": "x"}
        ])


def test_distinct_values(engine):
    assert fetch_distinct_values(engine, "orders", "category") == ["Books", "Games", "Other"]


def test_insights_are_data_derived():
    frame = pd.DataFrame({"category": ["A", "B", "C"], "value": [10, 20, 5]})
    insights = build_rule_based_insights(frame, "category", "value")
    assert "Highest value: B (20.00)." in insights
    assert "Lowest value: C (5.00)." in insights


def test_insights_handle_empty_data():
    assert "Not enough data" in build_rule_based_insights(pd.DataFrame(), "x", "y")[0]


def test_percentage_change():
    assert percentage_change(120, 100) == 20
    assert percentage_change(80, 100) == -20
    assert percentage_change(10, 0) is None


def test_excel_export_returns_xlsx_bytes():
    payload = dataframe_to_excel(pd.DataFrame({"a": [1, 2]}))
    assert payload[:2] == b"PK"


def test_time_series_aggregation_monthly():
    frame = pd.DataFrame({
        "order_date": ["2026-01-01", "2026-01-20", "2026-02-03", "invalid"],
        "value": [10, 15, 7, 100],
    })
    result = aggregate_time_series(frame, "order_date", "value", "Monthly")
    assert result["value"].tolist() == [25, 7]


def test_time_series_rejects_unknown_granularity():
    with pytest.raises(ValueError):
        aggregate_time_series(pd.DataFrame({"d": [], "v": []}), "d", "v", "Hourly")


def test_table_preview_includes_all_columns_and_applies_filters(engine):
    result = fetch_table_preview(
        engine, "orders", [{"column": "region", "operator": "=", "value": "South"}], max_rows=10
    )
    assert set(result.columns) == {"order_id", "category", "amount", "order_date", "region"}
    assert len(result) == 2
    assert set(result["region"]) == {"South"}
