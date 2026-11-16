"""Database connection lifecycle and non-secret connection profile storage."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import json
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import SQLAlchemyError


class ConnectionConfigurationError(ValueError):
    """Raised when connection settings are incomplete or invalid."""


@dataclass
class ConnectionConfig:
    database_type: str
    database: str = ""
    host: str = ""
    port: int | None = None
    username: str = ""
    password: str = ""
    sqlite_path: str = ""

    def profile_dict(self) -> dict[str, Any]:
        """Return profile-safe fields. Passwords are deliberately excluded."""
        return {
            "database_type": self.database_type,
            "database": self.database,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "sqlite_path": self.sqlite_path,
        }


def _validate_config(config: ConnectionConfig) -> None:
    kind = config.database_type.lower()
    if kind == "sqlite":
        if not config.sqlite_path.strip():
            raise ConnectionConfigurationError("Select or enter a SQLite database file.")
        return
    if kind not in {"postgresql", "mysql"}:
        raise ConnectionConfigurationError("Supported databases are SQLite, PostgreSQL and MySQL.")
    missing = []
    if not config.host.strip():
        missing.append("host")
    if not config.database.strip():
        missing.append("database name")
    if not config.username.strip():
        missing.append("username")
    if not config.password:
        missing.append("password")
    if missing:
        raise ConnectionConfigurationError("Missing required field(s): " + ", ".join(missing))
    if not config.port or not (1 <= int(config.port) <= 65535):
        raise ConnectionConfigurationError("Port must be a number between 1 and 65535.")


def build_engine(config: ConnectionConfig) -> Engine:
    """Build a SQLAlchemy engine without logging credentials."""
    _validate_config(config)
    kind = config.database_type.lower()

    if kind == "sqlite":
        path = Path(config.sqlite_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        url = URL.create("sqlite", database=str(path))
        return create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 15},
            pool_pre_ping=True,
        )

    if kind == "postgresql":
        url = URL.create(
            "postgresql+psycopg",
            username=config.username,
            password=config.password,
            host=config.host,
            port=int(config.port or 5432),
            database=config.database,
        )
    else:
        url = URL.create(
            "mysql+pymysql",
            username=config.username,
            password=config.password,
            host=config.host,
            port=int(config.port or 3306),
            database=config.database,
            query={"charset": "utf8mb4"},
        )

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=5,
        pool_timeout=15,
    )


def test_connection(config: ConnectionConfig) -> dict[str, Any]:
    """Open a temporary connection, run SELECT 1, and dispose the test engine."""
    engine = build_engine(config)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            dialect = engine.dialect.name
            server_version = getattr(engine.dialect, "server_version_info", None)
        return {
            "success": True,
            "dialect": dialect,
            "server_version": ".".join(map(str, server_version)) if server_version else "Not reported",
            "message": "Connection test successful.",
        }
    except SQLAlchemyError as exc:
        # Do not expose a rendered URL, which could contain sensitive connection details.
        raise ConnectionError(f"Could not connect to {config.database_type}: {exc.__class__.__name__}: {exc}") from None
    finally:
        engine.dispose()


class ConnectionManager:
    """Owns one active SQLAlchemy engine for the current application session."""

    def __init__(self) -> None:
        self.engine: Engine | None = None
        self.config: ConnectionConfig | None = None
        self.last_config: ConnectionConfig | None = None
        self.connected: bool = False

    def connect(self, config: ConnectionConfig) -> dict[str, Any]:
        """Validate and replace the active connection only after a successful probe."""
        candidate = build_engine(config)
        try:
            with candidate.connect() as conn:
                conn.execute(text("SELECT 1"))
            old_engine = self.engine
            self.engine = candidate
            self.config = config
            self.last_config = config
            self.connected = True
            if old_engine is not None:
                old_engine.dispose()
            return {
                "success": True,
                "dialect": candidate.dialect.name,
                "database": config.database if config.database else Path(config.sqlite_path).name,
                "message": "Connected successfully.",
            }
        except Exception:
            candidate.dispose()
            raise

    def reconnect(self) -> dict[str, Any]:
        config = self.config or self.last_config
        if config is None:
            raise ConnectionConfigurationError("There is no previous connection profile to reconnect.")
        return self.connect(config)

    def disconnect(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
        self.engine = None
        # Keep the last non-secret/ in-memory config so the Reconnect action works.
        # Password remains only in this process's memory and is never persisted to disk.
        if self.config is not None:
            self.last_config = self.config
        self.config = None
        self.connected = False

    def connection_info(self) -> dict[str, str] | None:
        if not self.connected or self.config is None or self.engine is None:
            return None
        database = self.config.database or Path(self.config.sqlite_path).name
        return {
            "database_type": self.engine.dialect.name,
            "database": database,
            "endpoint": (
                self.config.sqlite_path if self.config.database_type.lower() == "sqlite"
                else f"{self.config.host}:{self.config.port}/{self.config.database}"
            ),
        }


class ProfileStore:
    """Persist profile metadata only; credentials/passwords are never stored."""

    def __init__(self, path: str | Path = "data/connection_profiles.json") -> None:
        self.path = Path(path)

    def list_profiles(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, name: str, config: ConnectionConfig) -> None:
        name = name.strip()
        if not name:
            raise ConnectionConfigurationError("Enter a profile name.")
        profiles = self.list_profiles()
        profiles[name] = config.profile_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(profiles, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def delete(self, name: str) -> None:
        profiles = self.list_profiles()
        profiles.pop(name, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(profiles, indent=2), encoding="utf-8")
