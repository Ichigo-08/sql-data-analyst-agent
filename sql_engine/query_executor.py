"""Read-only SQL execution with limits, parameter binding and timing."""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter, monotonic
from typing import Any
import pandas as pd

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config.settings import settings
from sql_engine.sql_validator import validate_read_only_sql, SQLValidationError


@dataclass
class QueryExecutionResult:
    dataframe: pd.DataFrame
    rows_returned: int
    elapsed_seconds: float
    truncated: bool
    message: str


class QueryExecutionError(RuntimeError):
    """Raised when a validated query cannot be executed."""


def _apply_timeout(connection, dialect: str, timeout_seconds: int):
    """Apply per-query timeout controls where the database supports them."""
    raw = None
    if dialect == "sqlite":
        raw = connection.connection.driver_connection
        deadline = monotonic() + timeout_seconds

        def progress_handler():
            return 1 if monotonic() > deadline else 0

        raw.set_progress_handler(progress_handler, 1000)
    elif dialect == "postgresql":
        connection.execute(
            text("SET LOCAL statement_timeout = :timeout_ms"),
            {"timeout_ms": int(timeout_seconds * 1000)},
        )
    # MySQL timeout semantics differ by server/version. A dedicated read-only
    # DB user and server-side execution limits are recommended for production.
    return raw


def execute_read_only_query(
    engine: Engine,
    query: str,
    parameters: dict[str, Any] | None = None,
    max_rows: int | None = None,
    timeout_seconds: int | None = None,
    max_query_length: int | None = None,
) -> QueryExecutionResult:
    """Validate and execute a single read-only SELECT, returning at most max_rows."""
    max_rows = max_rows or settings.max_result_rows
    timeout_seconds = timeout_seconds or settings.query_timeout_seconds
    max_query_length = max_query_length or settings.max_query_length

    if not 1 <= int(max_rows) <= 100_000:
        raise ValueError("Maximum result rows must be between 1 and 100,000.")
    if not 1 <= int(timeout_seconds) <= 300:
        raise ValueError("Query timeout must be between 1 and 300 seconds.")
    if parameters is not None and not isinstance(parameters, dict):
        raise ValueError("Query parameters must be supplied as a JSON object.")

    validation = validate_read_only_sql(
        query, engine.dialect.name, max_query_length=max_query_length
    )
    started = perf_counter()
    connection = None
    sqlite_raw = None
    try:
        connection = engine.connect()
        dialect = engine.dialect.name

        if dialect == "sqlite":
            # query_only is connection-scoped. It is turned off before returning
            # the pooled connection, even if execution raises an exception.
            connection.exec_driver_sql("PRAGMA query_only = ON")
            sqlite_raw = _apply_timeout(connection, dialect, timeout_seconds)
        else:
            # Make the read-only transaction the first statement in the transaction.
            # PostgreSQL requires SET TRANSACTION READ ONLY before other transaction work.
            if dialect in {"postgresql", "mysql"}:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            if dialect == "postgresql":
                _apply_timeout(connection, dialect, timeout_seconds)

        result = connection.execution_options(stream_results=True).execute(
            text(validation.normalized_sql), parameters or {}
        )
        if not result.returns_rows:
            raise QueryExecutionError("The statement did not return rows.")

        rows = result.fetchmany(int(max_rows) + 1)
        truncated = len(rows) > int(max_rows)
        rows = rows[:int(max_rows)]
        columns = list(result.keys())
        dataframe = pd.DataFrame([dict(row._mapping) for row in rows], columns=columns)
        elapsed = perf_counter() - started
        result.close()

        if dialect != "sqlite":
            connection.rollback()
        return QueryExecutionResult(
            dataframe=dataframe,
            rows_returned=len(dataframe),
            elapsed_seconds=elapsed,
            truncated=truncated,
            message=(
                f"Query executed successfully. Results limited to {max_rows:,} rows."
                if truncated else "Query executed successfully."
            ),
        )
    except (SQLValidationError, ValueError, QueryExecutionError):
        raise
    except Exception as exc:
        # Do not include connection URLs or credentials in error messages.
        raise QueryExecutionError(
            f"Query execution failed ({exc.__class__.__name__}). Check SQL syntax, "
            "parameter names, permissions, and database availability."
        ) from None
    finally:
        if connection is not None:
            try:
                if sqlite_raw is not None:
                    sqlite_raw.set_progress_handler(None, 0)
                    connection.rollback()
                    connection.exec_driver_sql("PRAGMA query_only = OFF")
                else:
                    connection.rollback()
            except Exception:
                pass
            connection.close()
