
from pathlib import Path

from sqlalchemy import create_engine

from ai.schema_context import get_database_schema


database_path = Path(
    r"C:\Users\keert\Downloads\sql_data_analyst_phase7\sql_data_analyst_phase1\data\sample.db"
)

engine = create_engine(
    f"sqlite:///{database_path.as_posix()}"
)

try:
    schema = get_database_schema(engine)

    print("DATABASE SCHEMA RETRIEVED SUCCESSFULLY")
    print("=" * 50)
    print(schema)

finally:
    engine.dispose()
