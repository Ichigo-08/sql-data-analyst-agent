"""Unit tests for Phase 2 database connection management."""
from pathlib import Path
import json

import pytest
from sqlalchemy import text

from database.connection_manager import (
    ConnectionConfig,
    ConnectionConfigurationError,
    ConnectionManager,
    ProfileStore,
    build_engine,
    test_connection as check_connection,
)


def test_sqlite_engine_and_test_connection(tmp_path):
    db = tmp_path / "unit_test.db"
    result = check_connection(ConnectionConfig("sqlite", sqlite_path=str(db)))
    assert result["success"] is True
    assert result["dialect"] == "sqlite"
    assert db.exists()


def test_manager_connect_disconnect_reconnect(tmp_path):
    db = tmp_path / "manager.db"
    manager = ConnectionManager()
    config = ConnectionConfig("sqlite", sqlite_path=str(db))
    result = manager.connect(config)
    assert result["success"] is True
    assert manager.connected is True
    assert manager.engine is not None
    with manager.engine.connect() as conn:
        assert conn.execute(text("SELECT 42")).scalar_one() == 42
    manager.disconnect()
    assert manager.connected is False
    assert manager.engine is None
    result = manager.reconnect()
    assert result["success"] is True
    manager.disconnect()


def test_reconnect_preserves_profile_until_replaced(tmp_path):
    manager = ConnectionManager()
    config = ConnectionConfig("sqlite", sqlite_path=str(tmp_path / "reconnect.db"))
    manager.connect(config)
    manager.engine.dispose()
    result = manager.reconnect()
    assert result["success"] is True
    manager.disconnect()


def test_invalid_database_type_rejected():
    with pytest.raises(ConnectionConfigurationError):
        build_engine(ConnectionConfig("oracle"))


def test_missing_postgres_fields_rejected():
    with pytest.raises(ConnectionConfigurationError):
        build_engine(ConnectionConfig("postgresql"))


def test_profile_store_never_persists_password(tmp_path):
    path = tmp_path / "profiles.json"
    store = ProfileStore(path)
    config = ConnectionConfig(
        "postgresql", database="analytics", host="db.example",
        port=5432, username="analyst", password="super-secret"
    )
    store.save("college-db", config)
    raw = path.read_text(encoding="utf-8")
    assert "super-secret" not in raw
    saved = json.loads(raw)["college-db"]
    assert saved["database"] == "analytics"
    assert "password" not in saved


def test_profile_delete(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    store.save("local", ConnectionConfig("sqlite", sqlite_path="data/local.db"))
    store.delete("local")
    assert store.list_profiles() == {}


def test_postgres_and_mysql_engine_urls_are_built_without_connecting():
    pytest.importorskip("psycopg")
    pytest.importorskip("pymysql")
    pg = build_engine(ConnectionConfig(
        "postgresql", database="analytics", host="localhost",
        port=5432, username="analyst", password="not-persisted"
    ))
    mysql = build_engine(ConnectionConfig(
        "mysql", database="analytics", host="localhost",
        port=3306, username="analyst", password="not-persisted"
    ))
    assert pg.dialect.name == "postgresql"
    assert mysql.dialect.name == "mysql"
    assert "not-persisted" not in pg.url.render_as_string(hide_password=True)
    pg.dispose()
    mysql.dispose()
