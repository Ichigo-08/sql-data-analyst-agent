"""Database-agnostic schema inspection and paginated table access."""
from __future__ import annotations

from typing import Any
import pandas as pd

from sqlalchemy import (
    MetaData, Table, cast, String, select, func, or_
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.inspection import inspect as sqlalchemy_inspect


def list_tables(engine: Engine, include_views: bool = True) -> list[dict[str, str]]:
    """Return table and optionally view names from the connected database."""
    inspector = sqlalchemy_inspect(engine)
    result = [{"name": name, "type": "table"} for name in inspector.get_table_names()]
    if include_views:
        result.extend({"name": name, "type": "view"} for name in inspector.get_view_names())
    return sorted(result, key=lambda item: (item["type"], item["name"].lower()))


def get_table_details(engine: Engine, table_name: str) -> dict[str, Any]:
    """Return columns, primary key and foreign keys for a validated existing table."""
    inspector = sqlalchemy_inspect(engine)
    available = {item["name"] for item in list_tables(engine)}
    if table_name not in available:
        raise ValueError(f"Table or view '{table_name}' does not exist in the connected database.")

    columns = inspector.get_columns(table_name)
    pk = inspector.get_pk_constraint(table_name) or {}
    foreign_keys = inspector.get_foreign_keys(table_name) or []
    indexes = inspector.get_indexes(table_name) or []

    pk_columns = set(pk.get("constrained_columns") or [])
    normalized_columns = []
    for col in columns:
        normalized_columns.append({
            "name": col.get("name"),
            "type": str(col.get("type")),
            "nullable": bool(col.get("nullable", True)),
            "default": str(col.get("default")) if col.get("default") is not None else None,
            "primary_key": col.get("name") in pk_columns,
        })

    normalized_fks = []
    for fk in foreign_keys:
        normalized_fks.append({
            "name": fk.get("name"),
            "columns": fk.get("constrained_columns") or [],
            "referred_table": fk.get("referred_table"),
            "referred_columns": fk.get("referred_columns") or [],
            "referred_schema": fk.get("referred_schema"),
        })

    return {
        "table_name": table_name,
        "columns": normalized_columns,
        "primary_key": sorted(pk_columns),
        "foreign_keys": normalized_fks,
        "indexes": [
            {"name": idx.get("name"), "columns": idx.get("column_names") or [],
             "unique": bool(idx.get("unique", False))}
            for idx in indexes
        ],
    }


def get_row_count(engine: Engine, table_name: str) -> int:
    """Count rows in an existing table/view using a quoted reflected identifier."""
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def get_relationships(engine: Engine) -> list[dict[str, Any]]:
    """Return all declared foreign-key relationships in the database."""
    relationships = []
    for item in list_tables(engine, include_views=False):
        details = get_table_details(engine, item["name"])
        for fk in details["foreign_keys"]:
            relationships.append({
                "source_table": item["name"],
                "source_columns": fk["columns"],
                "target_table": fk["referred_table"],
                "target_columns": fk["referred_columns"],
                "constraint": fk["name"],
            })
    return relationships


def fetch_table_page(
    engine: Engine,
    table_name: str,
    page: int = 1,
    page_size: int = 50,
    search_column: str | None = None,
    search_text: str | None = None,
) -> tuple[pd.DataFrame, int]:
    """Fetch one page and total matching row count. Search values are bound safely."""
    if page < 1:
        raise ValueError("Page must be 1 or greater.")
    if not 1 <= page_size <= 500:
        raise ValueError("Page size must be between 1 and 500.")

    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    stmt = select(table)
    count_stmt = select(func.count()).select_from(table)

    if search_text and search_text.strip():
        if not search_column or search_column not in table.c:
            raise ValueError("Select a valid column before searching.")
        predicate = cast(table.c[search_column], String).ilike(f"%{search_text.strip()}%")
        stmt = stmt.where(predicate)
        count_stmt = count_stmt.where(predicate)

    offset = (page - 1) * page_size
    stmt = stmt.limit(page_size).offset(offset)

    with engine.connect() as connection:
        total = int(connection.execute(count_stmt).scalar_one())
        rows = connection.execute(stmt).mappings().all()
    return pd.DataFrame([dict(row) for row in rows]), total


def get_column_statistics(engine: Engine, table_name: str, column_name: str) -> dict[str, Any]:
    """Return simple descriptive statistics for one column without loading the whole table."""
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    if column_name not in table.c:
        raise ValueError(f"Column '{column_name}' does not exist in '{table_name}'.")

    col = table.c[column_name]
    numeric = getattr(col.type, "_type_affinity", None)
    is_numeric = str(numeric).lower().find("numeric") >= 0 or str(numeric).lower().find("integer") >= 0 or str(numeric).lower().find("float") >= 0

    expressions = [
        func.count().label("row_count"),
        func.count(col).label("non_null_count"),
    ]
    if is_numeric:
        expressions.extend([
            func.min(col).label("minimum"),
            func.max(col).label("maximum"),
            func.avg(col).label("average"),
        ])
    with engine.connect() as connection:
        result = connection.execute(select(*expressions).select_from(table)).mappings().one()
    stats = dict(result)
    stats["null_count"] = int(stats["row_count"] - stats["non_null_count"])
    return stats
