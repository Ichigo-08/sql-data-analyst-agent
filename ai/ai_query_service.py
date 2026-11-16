
from ai.sql_generator import generate_sql
from ai.schema_context import get_database_schema

from sql_engine.sql_validator import (
    validate_read_only_sql,
    SQLValidationError,
)

from sql_engine.query_executor import execute_read_only_query


def generate_and_validate(engine, question: str):
    """
    Generate SQL using Gemini and validate it.
    Does not execute the generated query.
    """

    if engine is None:
        raise ValueError("No active database connection.")

    schema = get_database_schema(engine)

    generated_sql = generate_sql(
        question=question,
        schema=schema,
        dialect=engine.dialect.name,
    )

    validation = validate_read_only_sql(
        generated_sql,
        engine.dialect.name,
    )

    return {
        "question": question,
        "sql": validation.normalized_sql,
        "valid": validation.valid,
        "message": validation.message,
    }


def execute_approved_ai_query(engine, generated_sql: str):
    """
    Execute an AI-generated query only after it has been
    validated by the existing read-only query executor.
    """

    if engine is None:
        raise ValueError("No active database connection.")

    return execute_read_only_query(
        engine=engine,
        query=generated_sql,
    )
