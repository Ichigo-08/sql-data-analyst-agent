
from pathlib import Path
from sqlalchemy import create_engine

from ai.schema_context import get_database_schema
from ai.sql_generator import generate_sql


DATABASE_PATH = Path(
    r"C:\Users\keert\Downloads\sql_data_analyst_phase7\sql_data_analyst_phase1\data\sample.db"
)

engine = create_engine(
    f"sqlite:///{DATABASE_PATH.as_posix()}"
)

try:
    # Retrieve the actual database schema
    schema = get_database_schema(engine)

    print("Actual database schema loaded successfully.")

    # Ask Gemini a question
    question = "Show the top 10 customers by total spending"

    print("\nUser question:")
    print(question)

    # Generate SQL using actual schema
    generated_query = generate_sql(
        question=question,
        schema=schema,
        dialect="SQLite"
    )

    print("\nGenerated SQL:")
    print(generated_query)

finally:
    engine.dispose()
