"""Generate parameterized, read-only SELECT queries from visual builder settings."""
from __future__ import annotations

from typing import Any
from sqlalchemy import inspect as sqlalchemy_inspect


AGGREGATIONS = {"None": None, "COUNT": "COUNT", "SUM": "SUM", "AVG": "AVG", "MIN": "MIN", "MAX": "MAX"}
FILTER_OPERATORS = ["=", "!=", ">", ">=", "<", "<=", "LIKE", "IN", "IS NULL", "IS NOT NULL"]


class QueryBuilderError(ValueError):
    """Raised when visual query-builder settings are invalid."""


def _quote(engine, identifier: str) -> str:
    return engine.dialect.identifier_preparer.quote(identifier)


def get_table_columns(engine, table_name: str) -> list[dict[str, Any]]:
    inspector = sqlalchemy_inspect(engine)
    known_tables = set(inspector.get_table_names()) | set(inspector.get_view_names())
    if table_name not in known_tables:
        raise QueryBuilderError(f"Unknown table or view: {table_name}")
    return inspector.get_columns(table_name)


def get_join_candidates(engine, base_table: str, join_table: str) -> list[dict[str, Any]]:
    """Return declared FK paths between two selected tables, in either direction."""
    inspector = sqlalchemy_inspect(engine)
    candidates = []
    for fk in inspector.get_foreign_keys(base_table) or []:
        if fk.get("referred_table") == join_table:
            candidates.append({
                "base_column": (fk.get("constrained_columns") or [None])[0],
                "join_column": (fk.get("referred_columns") or [None])[0],
                "relationship": f"{base_table} → {join_table}",
            })
    for fk in inspector.get_foreign_keys(join_table) or []:
        if fk.get("referred_table") == base_table:
            candidates.append({
                "base_column": (fk.get("referred_columns") or [None])[0],
                "join_column": (fk.get("constrained_columns") or [None])[0],
                "relationship": f"{join_table} → {base_table}",
            })
    return [item for item in candidates if item["base_column"] and item["join_column"]]


def _convert_filter_value(column, raw_value: str):
    try:
        python_type = column["type"].python_type
    except (AttributeError, NotImplementedError):
        python_type = str
    value = raw_value
    if python_type is bool:
        lowered = raw_value.strip().lower()
        if lowered not in {"true", "false", "1", "0"}:
            raise QueryBuilderError("Boolean filters must use true, false, 1 or 0.")
        return lowered in {"true", "1"}
    if python_type in {int, float}:
        try:
            return python_type(raw_value)
        except ValueError:
            raise QueryBuilderError(f"Enter a valid {python_type.__name__} filter value.") from None
    return value


def generate_select_query(
    engine,
    *,
    base_table: str,
    selected_columns: list[str],
    aggregation: str = "None",
    aggregation_column: str | None = None,
    join_table: str | None = None,
    join_type: str = "INNER",
    base_join_column: str | None = None,
    joined_column: str | None = None,
    filters: list[dict[str, str]] | None = None,
    order_by: str | None = None,
    order_direction: str = "ASC",
    limit: int = 1000,
) -> tuple[str, dict[str, Any]]:
    """Build one parameterized SELECT statement; values never enter SQL literals."""
    inspector = sqlalchemy_inspect(engine)
    tables = set(inspector.get_table_names()) | set(inspector.get_view_names())
    if base_table not in tables:
        raise QueryBuilderError("Choose a valid base table.")
    if not 1 <= int(limit) <= 100_000:
        raise QueryBuilderError("Result limit must be between 1 and 100,000.")

    base_cols = get_table_columns(engine, base_table)
    base_names = {item["name"] for item in base_cols}
    if not selected_columns and aggregation == "None":
        raise QueryBuilderError("Select at least one output column.")
    join_cols: list[dict[str, Any]] = []
    join_names: set[str] = set()
    if join_table:
        if join_table not in tables or join_table == base_table:
            raise QueryBuilderError("Choose a different valid table to join.")
        if join_type.upper() not in {"INNER", "LEFT", "RIGHT"}:
            raise QueryBuilderError("Join type must be INNER, LEFT or RIGHT.")
        join_cols = get_table_columns(engine, join_table)
        join_names = {item["name"] for item in join_cols}
        if not base_join_column or base_join_column not in base_names:
            raise QueryBuilderError("Choose a valid join key from the base table.")
        if not joined_column or joined_column not in join_names:
            raise QueryBuilderError("Choose a valid join key from the joined table.")
    elif base_join_column or joined_column:
        raise QueryBuilderError("Choose a joined table before specifying join keys.")

    join_names = {item["name"] for item in join_cols}
    available_names = base_names | join_names
    if any(
        (name.split(".", 1)[1] if "." in name else name) not in available_names
        for name in selected_columns
    ):
        raise QueryBuilderError("One or more selected columns do not belong to the selected tables.")

    def resolve_column(token: str) -> tuple[str, str]:
        if "." in token:
            owner, name = token.split(".", 1)
            if owner == base_table and name in base_names:
                return owner, name
            if owner == join_table and name in join_names:
                return owner, name
            raise QueryBuilderError(f"Column '{token}' is not available.")
        if token in base_names:
            return base_table, token
        if join_table and token in join_names:
            return join_table, token
        raise QueryBuilderError(f"Column '{token}' is not available.")

    aggregation = aggregation.upper()
    if aggregation not in {"NONE", "COUNT", "SUM", "AVG", "MIN", "MAX"}:
        raise QueryBuilderError("Unsupported aggregation.")
    if aggregation != "NONE":
        if aggregation == "COUNT" and aggregation_column in {None, "*"}:
            aggregate_expression = "COUNT(*)"
        else:
            owner, aggregate_name = resolve_column(aggregation_column)
            aggregate_expression = f"{aggregation}({_quote(engine, owner)}.{_quote(engine, aggregate_name)})"
    else:
        aggregate_expression = None

    # Alias output columns to avoid duplicate labels when joined tables share names.
    select_expressions = []
    output_aliases = {}
    for token in selected_columns:
        owner, name = resolve_column(token)
        alias = f"{owner}__{name}"
        output_aliases[token] = alias
        select_expressions.append(
            f"{_quote(engine, owner)}.{_quote(engine, name)} AS {_quote(engine, alias)}"
        )
    if aggregate_expression:
        select_expressions.append(f"{aggregate_expression} AS {_quote(engine, 'aggregation_value')}")
    if not select_expressions:
        raise QueryBuilderError("The query has no output columns.")

    q_base = _quote(engine, base_table)
    from_sql = q_base
    if join_table:
        q_join = _quote(engine, join_table)
        join_keyword = {"INNER": "INNER JOIN", "LEFT": "LEFT OUTER JOIN", "RIGHT": "RIGHT OUTER JOIN"}[join_type.upper()]
        from_sql += (
            f" {join_keyword} {q_join} ON "
            f"{q_base}.{_quote(engine, base_join_column)} = "
            f"{q_join}.{_quote(engine, joined_column)}"
        )

    where_parts = []
    parameters: dict[str, Any] = {}
    all_columns = {
        f"{base_table}.{item['name']}": item for item in base_cols
    }
    if join_table:
        all_columns.update({
            f"{join_table}.{item['name']}": item for item in join_cols
        })
    for index, rule in enumerate(filters or [], start=1):
        column_token = rule.get("column", "")
        operator = rule.get("operator", "=").upper()
        raw_value = rule.get("value", "")
        try:
            owner, column_name = resolve_column(column_token)
            column_metadata = all_columns.get(f"{owner}.{column_name}")
        except QueryBuilderError:
            column_metadata = None
            owner, column_name = "", ""
        if not column_metadata:
            raise QueryBuilderError(f"Filter {index}: choose a valid column.")
        if operator not in FILTER_OPERATORS:
            raise QueryBuilderError(f"Filter {index}: unsupported operator.")
        qualified = f"{_quote(engine, owner)}.{_quote(engine, column_name)}"
        if operator == "IS NULL":
            where_parts.append(f"{qualified} IS NULL")
        elif operator == "IS NOT NULL":
            where_parts.append(f"{qualified} IS NOT NULL")
        elif operator == "IN":
            values = [item.strip() for item in raw_value.split(",") if item.strip()]
            if not values:
                raise QueryBuilderError(f"Filter {index}: enter comma-separated values for IN.")
            placeholders = []
            for sub_index, value in enumerate(values, start=1):
                key = f"filter_{index}_{sub_index}"
                parameters[key] = _convert_filter_value(column_metadata, value)
                placeholders.append(f":{key}")
            where_parts.append(f"{qualified} IN ({', '.join(placeholders)})")
        else:
            if raw_value == "":
                raise QueryBuilderError(f"Filter {index}: enter a filter value.")
            key = f"filter_{index}"
            value = _convert_filter_value(column_metadata, raw_value)
            if operator == "LIKE":
                value = f"%{value}%"
            parameters[key] = value
            where_parts.append(f"{qualified} {operator} :{key}")

    sql = "SELECT " + ", ".join(select_expressions) + " FROM " + from_sql
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)

    if aggregation != "NONE":
        if selected_columns:
            group_expressions = []
            for name in selected_columns:
                group_expressions.append(_quote(engine, output_aliases[name]))
            sql += " GROUP BY " + ", ".join(group_expressions)

    if order_by:
        allowed_order = set(selected_columns)
        if aggregate_expression:
            allowed_order.add("aggregation_value")
        if order_by not in allowed_order:
            raise QueryBuilderError("Sort column must be one of the selected output columns.")
        direction = order_direction.upper()
        if direction not in {"ASC", "DESC"}:
            raise QueryBuilderError("Sort direction must be ASC or DESC.")
        order_alias = output_aliases.get(order_by, order_by)
        sql += f" ORDER BY {_quote(engine, order_alias)} {direction}"

    sql += f" LIMIT {int(limit)}"
    return sql, parameters
