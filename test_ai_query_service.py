
from pathlib import Path
from sqlalchemy import create_engine

from ai.ai_query_service import (
    generate_and_validate,
    execute_approved_ai_query,
)

database_path = Path(
    r"C:\Users\keert\Downloads\sql_data_analyst_phase7\sql_data_analyst_phase1\data\sample.db"
)

engine = create_engine(
    f"sqlite:///{database_path.as_posix()}"
)

try:
    question = "Show the top 10 customers by total spending"

    result = generate_and_validate(engine, question)

    print("GENERATED SQL:")
    print(result["sql"])

    print("\nVALIDATION:")
    print(result["message"])

    if result["valid"]:
        print("\nExecuting approved query...")

        execution = execute_approved_ai_query(
            engine,
            result["sql"],
        )

        print("\nQUERY RESULTS:")
        print(execution.dataframe.to_string(index=False))
        print("\nRows returned:", execution.rows_returned)

finally:
    engine.dispose()
