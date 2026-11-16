"""Tests for visual SQL query generation."""
import pytest
from sqlalchemy import create_engine, text

from sql_engine.query_builder import generate_select_query, QueryBuilderError


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'builder.db'}")
    with eng.begin() as conn:
        conn.execute(text("""
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                customer_name TEXT NOT NULL,
                region TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                amount REAL,
                status TEXT,
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
            )
        """))
        conn.execute(text("INSERT INTO customers VALUES (1, 'Asha', 'South'), (2, 'Ravi', 'North')"))
        conn.execute(text("INSERT INTO orders VALUES (101, 1, 100.0, 'Paid'), (102, 2, 50.0, 'Open')"))
    yield eng
    eng.dispose()


def test_basic_select_generation(engine):
    sql, params = generate_select_query(
        engine, base_table="customers", selected_columns=["customer_id", "customer_name"],
    )
    assert "SELECT" in sql and "customers" in sql
    assert params == {}


def test_filter_is_parameterized(engine):
    sql, params = generate_select_query(
        engine, base_table="customers", selected_columns=["customer_name"],
        filters=[{"column": "region", "operator": "=", "value": "South"}],
    )
    assert ":filter_1" in sql
    assert params == {"filter_1": "South"}
    assert "South" not in sql


def test_in_filter_parameters(engine):
    sql, params = generate_select_query(
        engine, base_table="customers", selected_columns=["customer_name"],
        filters=[{"column": "region", "operator": "IN", "value": "South,North"}],
    )
    assert "IN" in sql
    assert len(params) == 2


def test_aggregation_and_grouping(engine):
    sql, _ = generate_select_query(
        engine, base_table="orders", selected_columns=["status"],
        aggregation="SUM", aggregation_column="amount",
    )
    assert "SUM" in sql
    assert "GROUP BY" in sql


def test_foreign_key_join_generation(engine):
    sql, _ = generate_select_query(
        engine, base_table="customers", selected_columns=["customers.customer_name", "orders.amount"],
        join_table="orders", join_type="LEFT",
        base_join_column="customer_id", joined_column="customer_id",
    )
    assert "LEFT OUTER JOIN" in sql
    assert "customer_id" in sql


def test_invalid_column_rejected(engine):
    with pytest.raises(QueryBuilderError):
        generate_select_query(engine, base_table="customers", selected_columns=["password"])


def test_invalid_limit_rejected(engine):
    with pytest.raises(QueryBuilderError):
        generate_select_query(engine, base_table="customers", selected_columns=["customer_name"], limit=0)


def test_join_can_select_same_named_columns_without_ambiguity(engine):
    sql, _ = generate_select_query(
        engine, base_table="customers",
        selected_columns=["customers.customer_id", "orders.customer_id"],
        join_table="orders", join_type="INNER",
        base_join_column="customer_id", joined_column="customer_id",
    )
    assert "customers__customer_id" in sql
    assert "orders__customer_id" in sql
