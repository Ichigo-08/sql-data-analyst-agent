"""Convenience facade for schema inspection operations."""
from sqlalchemy.engine import Engine
from database.schema_inspector import (
    list_tables, get_table_details, get_row_count,
    get_relationships, fetch_table_page, get_column_statistics,
)


class DatabaseManager:
    def __init__(self, engine: Engine):
        self.engine = engine

    def tables(self):
        return list_tables(self.engine)

    def table_details(self, table_name: str):
        return get_table_details(self.engine, table_name)

    def row_count(self, table_name: str):
        return get_row_count(self.engine, table_name)

    def relationships(self):
        return get_relationships(self.engine)

    def preview(self, table_name: str, **kwargs):
        return fetch_table_page(self.engine, table_name, **kwargs)

    def column_statistics(self, table_name: str, column_name: str):
        return get_column_statistics(self.engine, table_name, column_name)
