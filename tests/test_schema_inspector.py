"""Tests for database schema inspection using temporary SQLite databases."""
import pytest
from sqlalchemy import create_engine, text

from database.schema_inspector import (
    list_tables, get_table_details, get_row_count,
    get_relationships, fetch_table_page, get_column_statistics,
)


@pytest.fixture
def sample_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema_test.db'}")
    with engine.begin() as conn:
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
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
            )
        """))
        conn.execute(text("""
            INSERT INTO customers VALUES
            (1, 'Asha', 'South'), (2, 'Ravi', 'North'), (3, 'Meera', 'South')
        """))
        conn.execute(text("""
            INSERT INTO orders VALUES
            (101, 1, 120.5), (102, 1, 80.0), (103, 2, 50.0)
        """))
    yield engine
    engine.dispose()


def test_list_tables(sample_engine):
    names = [item["name"] for item in list_tables(sample_engine)]
    assert names == ["customers", "orders"]


def test_table_details_primary_and_foreign_keys(sample_engine):
    customers = get_table_details(sample_engine, "customers")
    orders = get_table_details(sample_engine, "orders")
    assert customers["primary_key"] == ["customer_id"]
    assert orders["primary_key"] == ["order_id"]
    assert orders["foreign_keys"][0]["referred_table"] == "customers"


def test_row_count(sample_engine):
    assert get_row_count(sample_engine, "orders") == 3


def test_relationship_discovery(sample_engine):
    relationships = get_relationships(sample_engine)
    assert len(relationships) == 1
    assert relationships[0]["source_table"] == "orders"
    assert relationships[0]["target_table"] == "customers"


def test_pagination_and_search(sample_engine):
    page, total = fetch_table_page(sample_engine, "customers", page=1, page_size=2)
    assert len(page) == 2
    assert total == 3
    found, found_total = fetch_table_page(
        sample_engine, "customers", search_column="region", search_text="South"
    )
    assert found_total == 2
    assert set(found["customer_name"]) == {"Asha", "Meera"}


def test_invalid_table_and_pagination_rejected(sample_engine):
    with pytest.raises(ValueError):
        get_table_details(sample_engine, "missing_table")
    with pytest.raises(ValueError):
        fetch_table_page(sample_engine, "customers", page=0)


def test_column_statistics(sample_engine):
    stats = get_column_statistics(sample_engine, "orders", "amount")
    assert stats["row_count"] == 3
    assert stats["non_null_count"] == 3
    assert stats["minimum"] == 50.0
    assert stats["maximum"] == 120.5
