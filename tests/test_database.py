"""Unit tests for SQLite database initialization, indexing, and connection safety."""

import sqlite3
import pytest
from pathlib import Path
from backend.database import get_connection, get_db, init_db, reset_db


@pytest.fixture
def test_db_path(tmp_path: Path):
    db_file = tmp_path / "test_vehiclegpt.db"
    init_db(db_file)
    return db_file


def test_database_initialization(test_db_path: Path):
    """Verify that tables and indexes are created properly."""
    with get_db(test_db_path) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "telemetry" in tables
        assert "vehicle_events" in tables
        assert "diagnostic_logs" in tables
        assert "ingestion_audit" in tables

        # Verify indexes
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = {row["name"] for row in cursor.fetchall()}
        assert "idx_telemetry_timestamp" in indexes
        assert "idx_telemetry_signal" in indexes
        assert "idx_events_timestamp" in indexes


def test_database_reset(test_db_path: Path):
    """Verify that reset_db empties all tables while keeping schema intact."""
    with get_db(test_db_path) as conn:
        conn.execute(
            "INSERT INTO telemetry (timestamp, signal_name, value, unit, source) VALUES (?, ?, ?, ?, ?);",
            ("2026-10-22T10:00:00Z", "vehicle_speed", 55.0, "km/h", "CAN_BUS"),
        )
        conn.commit()

    reset_db(test_db_path)

    with get_db(test_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM telemetry;").fetchone()[0]
        assert count == 0


def test_parameterized_query_safety(test_db_path: Path):
    """Ensure SQL injection attempts are safely treated as literal string values."""
    malicious_signal = "speed'; DROP TABLE telemetry; --"
    with get_db(test_db_path) as conn:
        conn.execute(
            "INSERT INTO telemetry (timestamp, signal_name, value, unit, source) VALUES (?, ?, ?, ?, ?);",
            ("2026-10-22T12:00:00Z", malicious_signal, 80.0, "km/h", "CAN_BUS"),
        )
        conn.commit()

        # Query using parameterization
        res = conn.execute("SELECT * FROM telemetry WHERE signal_name = ?;", (malicious_signal,)).fetchall()
        assert len(res) == 1
        assert res[0]["signal_name"] == malicious_signal

        # Verify table still exists
        table_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry';").fetchone()
        assert table_check is not None
