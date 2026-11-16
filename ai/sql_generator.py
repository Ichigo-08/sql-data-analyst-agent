
import re

from config.gemini_config import get_gemini_client, get_gemini_model


def generate_sql(question: str, schema: str, dialect: str = "SQLite") -> str:
    """
    Generate a read-only SQL query using Gemini.

    Args:
        question: User's natural-language question.
        schema: Connected database schema.
        dialect: SQL database dialect (SQLite, PostgreSQL, MySQL).

    Returns:
        Generated SQL query.

    Note:
        This function only generates SQL.
        It does not validate or execute the query.
    """

    if not question or not question.strip():
        raise ValueError("Please enter a question.")

    if not schema or not schema.strip():
        raise ValueError("Database schema is required.")

    client = get_gemini_client()
    model = get_gemini_model()

    prompt = f"""
You are an expert SQL analyst.

Generate one SQL query based on the user's question.

DATABASE DIALECT:
{dialect}

DATABASE SCHEMA:
{schema}

USER QUESTION:
{question}

STRICT RULES:
1. Generate only SELECT statements.
2. Read-only SELECT CTEs are allowed.
3. Never generate INSERT, UPDATE, DELETE, DROP,
   ALTER, CREATE, TRUNCATE or other modification statements.
4. Use only tables and columns present in the supplied schema.
5. Do not invent table names or column names.
6. Use the specified database dialect.
7. Do not execute the query.
8. Do not include explanations or Markdown code fences.
9. Return only the SQL query.
"""

    response = client.models.generate_content(
        model=model,
        contents=prompt
    )

    if not response.text:
        raise RuntimeError("Gemini returned an empty SQL response.")

    sql = response.text.strip()

    # Remove Markdown code fences if Gemini includes them.
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql)

    return sql.strip()
