"""SQLGlot-based read-only SQL validation."""
from __future__ import annotations

from dataclasses import dataclass
import sqlglot
from sqlglot import exp


class SQLValidationError(ValueError):
    """Raised when a query is not allowed by the read-only SQL policy."""


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    normalized_sql: str
    dialect: str
    message: str


DIALECT_MAP = {
    "sqlite": "sqlite",
    "postgresql": "postgres",
    "mysql": "mysql",
}


def validate_read_only_sql(
    query: str,
    database_dialect: str,
    max_query_length: int = 20_000,
) -> ValidationResult:
    """Allow exactly one SELECT statement (including read-only SELECT CTEs)."""
    if not isinstance(query, str) or not query.strip():
        raise SQLValidationError("Enter a SQL query.")
    if len(query) > max_query_length:
        raise SQLValidationError(
            f"Query exceeds the maximum permitted length of {max_query_length:,} characters."
        )

    dialect = DIALECT_MAP.get(database_dialect.lower())
    if dialect is None:
        raise SQLValidationError(f"Unsupported SQL dialect: {database_dialect}")

    try:
        statements = [item for item in sqlglot.parse(query, read=dialect) if item is not None]
    except sqlglot.errors.ParseError as exc:
        raise SQLValidationError(f"SQL syntax error: {exc}") from None

    if len(statements) != 1:
        raise SQLValidationError("Only one SQL statement can be executed at a time.")

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise SQLValidationError("Only SELECT statements and read-only SELECT CTEs are allowed.")

    # SELECT INTO and row-locking clauses can have side effects or lock records.
    if statement.args.get("into") is not None:
        raise SQLValidationError("SELECT INTO is not allowed in read-only mode.")
    if statement.args.get("locks"):
        raise SQLValidationError("SELECT statements that lock rows are not allowed.")

    # Defensive scan: reject any modifying/admin AST nodes nested in the expression.
    forbidden_names = (
        "Insert", "Update", "Delete", "Create", "Drop", "Alter",
        "Command", "Transaction", "Merge", "TruncateTable",
    )
    forbidden = tuple(
        node_type for node_type in (getattr(exp, name, None) for name in forbidden_names)
        if isinstance(node_type, type)
    )
    for node in statement.walk():
        if isinstance(node, forbidden):
            raise SQLValidationError(
                f"Unsafe SQL operation detected: {node.key.upper()}."
            )

    return ValidationResult(
        valid=True,
        normalized_sql=statement.sql(dialect=dialect),
        dialect=dialect,
        message="Query passed read-only SQL validation.",
    )
