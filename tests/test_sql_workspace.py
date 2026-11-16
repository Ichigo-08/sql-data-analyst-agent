"""Tests for SQL validation and read-only query execution."""
import pytest
from sqlalchemy import create_engine, text

from sql_engine.sql_validator import validate_read_only_sql, SQLValidationError
from sql_engine.query_executor import execute_read_only_query


@pytest.fixture
def engine(tmp_path):
    db = tmp_path / "query_test.db"
    eng = create_engine(f"sqlite:///{db}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)"))
        conn.execute(text("INSERT INTO people (name, age) VALUES ('Asha', 21), ('Ravi', 24), ('Meera', 22)"))
    yield eng
    eng.dispose()


@pytest.mark.parametrize("query", [
    "SELECT * FROM people",
    "WITH adults AS (SELECT * FROM people WHERE age >= 21) SELECT * FROM adults",
    "SELECT :value AS supplied_value",
])
def test_select_queries_allowed(query):
    assert validate_read_only_sql(query, "sqlite").valid


@pytest.mark.parametrize("query", [
    "DELETE FROM people",
    "UPDATE people SET age = 99",
    "INSERT INTO people VALUES (4, 'Test', 20)",
    "DROP TABLE people",
    "CREATE TABLE unsafe_table (id INTEGER)",
    "ALTER TABLE people ADD COLUMN email TEXT",
    "PRAGMA table_info(people)",
    "ATTACH DATABASE 'other.db' AS other",
    "SELECT * FROM people; DROP TABLE people",
    "SELECT * INTO new_table FROM people",
])
def test_unsafe_queries_rejected(query):
    with pytest.raises(SQLValidationError):
        validate_read_only_sql(query, "sqlite")


def test_empty_and_oversized_queries_rejected():
    with pytest.raises(SQLValidationError):
        validate_read_only_sql("  ", "sqlite")
    with pytest.raises(SQLValidationError):
        validate_read_only_sql("SELECT 1", "sqlite", max_query_length=3)


def test_execution_returns_rows_and_timing(engine):
    result = execute_read_only_query(engine, "SELECT name, age FROM people ORDER BY id")
    assert result.rows_returned == 3
    assert list(result.dataframe["name"]) == ["Asha", "Ravi", "Meera"]
    assert result.elapsed_seconds >= 0
    assert not result.truncated


def test_parameterized_execution(engine):
    result = execute_read_only_query(
        engine, "SELECT name FROM people WHERE age > :minimum",
        parameters={"minimum": 21}
    )
    assert list(result.dataframe["name"]) == ["Ravi", "Meera"]


def test_result_limit(engine):
    result = execute_read_only_query(engine, "SELECT * FROM people", max_rows=2)
    assert result.rows_returned == 2
    assert result.truncated is True


def test_query_only_does_not_modify_database(engine):
    with pytest.raises(SQLValidationError):
        execute_read_only_query(engine, "DELETE FROM people")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM people")).scalar_one() == 3


def test_invalid_parameter_shape_rejected(engine):
    with pytest.raises(ValueError):
        execute_read_only_query(engine, "SELECT 1", parameters=["not", "an", "object"])
