"""DuckDB connection and schema setup.

Default location: %LOCALAPPDATA%\\nba_platform\\nba_platform.duckdb (outside the project
folder, so folder-sync tools such as Synology Drive never touch it; a sync client
corrupted the in-project file on 2026-10-17, see docs/decisions.md).
NBA_PLATFORM_DB optionally overrides it; NBA_PLATFORM_MEMORY_LIMIT (for example "3GB") caps DuckDB memory so it spills to disk when Windows runs short of commit memory.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def default_db_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share")
    return Path(base) / "nba_platform" / "nba_platform.duckdb"


DB_PATH = Path(os.environ.get("NBA_PLATFORM_DB") or default_db_path())
SCHEMA_SQL = PROJECT_ROOT / "sql" / "schema.sql"


def connect(path: Path | str = DB_PATH, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the database. Writers (the pipeline) run the DDL; read-only users never write."""
    if read_only:
        return _limited(duckdb.connect(str(path), read_only=True))
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = _limited(duckdb.connect(str(path)))
    init_schema(con)
    return con


def _limited(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Optional NBA_PLATFORM_MEMORY_LIMIT (for example "3GB"): DuckDB spills to disk instead of failing with an
    allocation error when Windows runs short of commit memory."""
    limit = os.environ.get("NBA_PLATFORM_MEMORY_LIMIT")
    if limit:
        con.execute(f"SET memory_limit = '{limit}'")
    return con


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
