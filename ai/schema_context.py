
from database.schema_inspector import (
    list_tables,
    get_table_details,
    get_relationships,
)


def get_database_schema(engine) -> str:
    """
    Retrieve the actual schema from the active SQLAlchemy engine.
    No database records are sent to Gemini.
    """

    if engine is None:
        raise ValueError("No active database connection.")

    tables = list_tables(engine, include_views=True)

    if not tables:
        raise ValueError("The connected database contains no tables.")

    schema_parts = []

    for item in tables:
        table_name = item["name"]
        details = get_table_details(engine, table_name)

        schema_parts.append(f"\nTABLE: {table_name}")
        schema_parts.append(f"TYPE: {item['type']}")
        schema_parts.append("COLUMNS:")

        for column in details["columns"]:
            schema_parts.append(
                f"- {column['name']} "
                f"({column['type']})"
            )

        if details["primary_key"]:
            schema_parts.append(
                "PRIMARY KEY: " +
                ", ".join(details["primary_key"])
            )

        for fk in details["foreign_keys"]:
            schema_parts.append(
                f"FOREIGN KEY: {', '.join(fk['columns'])} "
                f"REFERENCES {fk['referred_table']}"
                f"({', '.join(fk['referred_columns'])})"
            )

    relationships = get_relationships(engine)

    if relationships:
        schema_parts.append("\nDATABASE RELATIONSHIPS:")

        for relationship in relationships:
            schema_parts.append(
                f"{relationship['source_table']} "
                f"({', '.join(relationship['source_columns'])}) "
                f"-> {relationship['target_table']} "
                f"({', '.join(relationship['target_columns'])})"
            )

    return "\n".join(schema_parts)
