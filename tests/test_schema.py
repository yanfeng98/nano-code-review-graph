"""Tests that a fresh database is created at the complete latest schema.

This fork has no migration machinery: ``_SCHEMA_SQL`` is the single source
of truth and builds the full schema (including the tables that used to be
created by migrations v2-v9) on first open. These tests pin the fresh-schema
invariants that migration tests used to cover.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from code_review_graph.graph import GraphStore

REQUIRED_TABLES = {
    "nodes",
    "edges",
    "metadata",
    "flows",
    "flow_memberships",
    "communities",
    "nodes_fts",
    "community_summaries",
    "flow_snapshots",
    "risk_index",
}


class TestFreshSchema:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()  # release the handle before GraphStore reopens it on Windows
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_all_tables_exist(self):
        tables = _get_table_names(self.store._conn)
        assert REQUIRED_TABLES <= tables

    def test_nodes_columns(self):
        columns = _get_columns(self.store._conn, "nodes")
        assert {"signature", "community_id"} <= columns

    def test_edges_columns(self):
        columns = _get_columns(self.store._conn, "edges")
        assert {"confidence", "confidence_tier"} <= columns

    def test_composite_edge_index_exists(self):
        rows = self.store._conn.execute("PRAGMA index_list(edges)").fetchall()
        indexes = {row[1] if isinstance(row, tuple) else row["name"] for row in rows}
        assert "idx_edges_composite" in indexes

    def test_no_schema_version_metadata(self):
        """The versioned-migration metadata key no longer exists."""
        rows = self.store._conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchall()
        assert rows == []

    def test_reopen_is_idempotent(self):
        self.store.close()
        self.store = GraphStore(self.tmp.name)
        assert REQUIRED_TABLES <= _get_table_names(self.store._conn)

    def test_usable_db_missing_index_self_heals(self):
        """A current-format DB missing the v8 composite index (an older but
        compatible DB) opens cleanly and gets the index re-added."""
        self.store._conn.execute("DROP INDEX idx_edges_composite")
        self.store._conn.commit()
        self.store.close()
        self.store = GraphStore(self.tmp.name)
        rows = self.store._conn.execute("PRAGMA index_list(edges)").fetchall()
        indexes = {row[1] if isinstance(row, tuple) else row["name"] for row in rows}
        assert "idx_edges_composite" in indexes


class TestStaleSchemaGuard:
    def test_stale_db_raises_clear_error(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        path = Path(tmp.name)
        try:
            # Old-format DB: base tables without the signature/community_id
            # columns and none of the secondary tables.
            conn = sqlite3.connect(str(path))
            conn.executescript(
                """
                CREATE TABLE nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    qualified_name TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    source_qualified TEXT NOT NULL,
                    target_qualified TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER DEFAULT 0,
                    extra TEXT DEFAULT '{}',
                    updated_at REAL NOT NULL
                );
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                """
            )
            conn.commit()
            conn.close()

            with pytest.raises(RuntimeError, match="rebuild"):
                GraphStore(path)
        finally:
            path.unlink(missing_ok=True)

    def test_empty_db_is_treated_as_fresh(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        path = Path(tmp.name)
        try:
            sqlite3.connect(str(path)).close()
            store = GraphStore(path)
            assert REQUIRED_TABLES <= _get_table_names(store._conn)
            store.close()
        finally:
            path.unlink(missing_ok=True)


def _get_table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    ).fetchall()
    return {row[0] if isinstance(row, (tuple, list)) else row["name"] for row in rows}


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] if isinstance(row, tuple) else row["name"] for row in rows}
