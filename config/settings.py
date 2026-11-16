"""Centralized environment-backed application settings."""
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "SQL Data Analyst")
    app_env: str = os.getenv("APP_ENV", "development")
    default_database_url: str = os.getenv(
        "DEFAULT_DATABASE_URL", "sqlite:///data/app.db"
    )
    query_timeout_seconds: int = int(os.getenv("QUERY_TIMEOUT_SECONDS", "30"))
    max_result_rows: int = int(os.getenv("MAX_RESULT_ROWS", "10000"))
    max_query_length: int = int(os.getenv("MAX_QUERY_LENGTH", "20000"))


settings = Settings()
