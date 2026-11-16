"""Safe, schema-aware CSV and Excel imports into the active database."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import BinaryIO

import pandas as pd
from sqlalchemy import MetaData, Table, func, inspect, select
from sqlalchemy.engine import Engine

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_IMPORT_ROWS = 250_000
_ALLOWED_TABLE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
_RESERVED_TABLES = {"sqlite_sequence", "sqlite_master", "sqlite_schema"}


class DataImportError(ValueError):
    """Raised when an uploaded file cannot safely be imported."""


def validate_table_name(table_name: str) -> str:
    name = str(table_name or "").strip()
    if not _ALLOWED_TABLE.fullmatch(name):
        raise DataImportError(
            "Table names must start with a letter and contain only letters, numbers, "
            "or underscores (maximum 63 characters)."
        )
    if name.lower() in _RESERVED_TABLES:
        raise DataImportError("That table name is reserved by the database.")
    return name


def read_uploaded_dataframe(
    filename: str,
    file_bytes: bytes,
    *,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    """Read a CSV or Excel upload with size, row and header validation."""
    suffix = Path(filename or "").suffix.lower()
    if not filename or suffix not in {".csv", ".xlsx"}:
        raise DataImportError("Upload a CSV, XLSX or XLS file.")
    if not file_bytes:
        raise DataImportError("The uploaded file is empty.")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise DataImportError("File exceeds the 50 MB upload limit.")

    try:
        stream = BytesIO(file_bytes)
        if suffix == ".csv":
            frame = pd.read_csv(stream, nrows=MAX_IMPORT_ROWS + 1)
        else:
            frame = pd.read_excel(stream, sheet_name=sheet_name, nrows=MAX_IMPORT_ROWS + 1)
    except Exception as exc:
        raise DataImportError(f"Could not read the uploaded file: {exc.__class__.__name__}.") from None

    if not isinstance(frame, pd.DataFrame):
        raise DataImportError("Select one worksheet to import.")
    if len(frame) > MAX_IMPORT_ROWS:
        raise DataImportError(f"The file exceeds the {MAX_IMPORT_ROWS:,}-row import limit.")
    if frame.empty:
        raise DataImportError("The file contains no data rows.")

    columns = [str(column).strip() for column in frame.columns]
    if any(not column for column in columns):
        raise DataImportError("Every column must have a non-empty header.")
    normalized = [column.casefold() for column in columns]
    if len(set(normalized)) != len(normalized):
        raise DataImportError("Column names must be unique (ignoring letter case).")
    frame.columns = columns
    return frame


def get_excel_sheet_names(filename: str, file_bytes: bytes) -> list[str]:
    """Return worksheet names for a valid Excel upload."""
    if Path(filename or "").suffix.lower() != ".xlsx":
        return []
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise DataImportError("File exceeds the 50 MB upload limit.")
    try:
        return list(pd.ExcelFile(BytesIO(file_bytes)).sheet_names)
    except Exception as exc:
        raise DataImportError(f"Could not inspect the Excel file: {exc.__class__.__name__}.") from None


def import_dataframe(
    engine: Engine,
    dataframe: pd.DataFrame,
    table_name: str,
    *,
    if_exists: str = "fail",
    confirm_replace: bool = False,
) -> dict[str, int | str]:
    """Import a DataFrame transactionally into the active SQLAlchemy database.

    Existing tables are never overwritten unless replace is explicitly selected
    and confirm_replace=True. Append requires an exact set of matching columns.
    """
    name = validate_table_name(table_name)
    if if_exists not in {"fail", "append", "replace"}:
        raise DataImportError("Choose fail, append or replace for an existing table.")
    if if_exists == "replace" and not confirm_replace:
        raise DataImportError("Confirm replacement before overwriting an existing table.")
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        raise DataImportError("There are no data rows to import.")
    if len(dataframe) > MAX_IMPORT_ROWS:
        raise DataImportError(f"The import exceeds the {MAX_IMPORT_ROWS:,}-row limit.")

    frame = dataframe.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    if any(not column for column in frame.columns):
        raise DataImportError("Every column must have a non-empty name.")
    normalized = [column.casefold() for column in frame.columns]
    if len(set(normalized)) != len(normalized):
        raise DataImportError("Column names must be unique (ignoring letter case).")

    try:
        with engine.begin() as connection:
            exists = inspect(connection).has_table(name)
            if exists and if_exists == "fail":
                raise DataImportError(f"Table '{name}' already exists. Choose append or explicitly confirm replace.")
            if exists and if_exists == "append":
                existing_columns = [column["name"] for column in inspect(connection).get_columns(name)]
                if {c.casefold() for c in existing_columns} != {c.casefold() for c in frame.columns}:
                    raise DataImportError(
                        "Append requires the uploaded columns to match the existing table columns."
                    )
                # Match the target table's column order for predictable inserts.
                frame = frame[existing_columns]
            frame.to_sql(
                name,
                con=connection,
                if_exists="append" if exists and if_exists == "append" else ("replace" if exists else "fail"),
                index=False,
                chunksize=1000,
            )
            imported_table = Table(name, MetaData(), autoload_with=connection)
            final_count = int(connection.execute(select(func.count()).select_from(imported_table)).scalar_one())
        return {"table_name": name, "imported_rows": int(len(dataframe)), "total_rows": final_count}
    except DataImportError:
        raise
    except Exception as exc:
        raise DataImportError(f"Import failed: {exc.__class__.__name__}: {exc}") from None
