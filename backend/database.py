"""SQLite database setup, schema management, and connection utilities for VehicleGPT."""

import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator
from backend.config import DB_ABSOLUTE_PATH

SCHEMA_SQL = """
-- Telemetry Table
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,         -- ISO 8601 UTC
    signal_name TEXT NOT NULL,       -- Normalized signal name
    value REAL NOT NULL,             -- Numerical value
    unit TEXT NOT NULL,              -- Engineering unit (e.g., km/h, °C, %)
    source TEXT NOT NULL             -- Source bus or subsystem (e.g., CAN_BUS, BMS_HAL)
);

-- Vehicle Events Table
CREATE TABLE IF NOT EXISTS vehicle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,         -- ISO 8601 UTC
    event_type TEXT NOT NULL,        -- e.g., ADAS_DISENGAGEMENT, DIAGNOSTIC_WARNING
    severity TEXT NOT NULL,          -- INFO, WARNING, CRITICAL
    description TEXT NOT NULL,       -- Human-readable context
    source TEXT NOT NULL,            -- e.g., ADAS_ECU, BMS_DIAGNOSTICS
    metadata TEXT                    -- JSON string with supplementary attributes
);

-- Diagnostic Trouble Code (DTC) Logs
CREATE TABLE IF NOT EXISTS diagnostic_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    dtc_code TEXT NOT NULL,
    ecu TEXT NOT NULL,
    status TEXT NOT NULL,            -- CONFIRMED, PENDING, CLEARED
    description TEXT NOT NULL
);

-- Ingestion and Data Quality Audit Table
CREATE TABLE IF NOT EXISTS ingestion_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,            -- SUCCESS, REJECTED, NORMALIZED
    reason TEXT,
    raw_payload TEXT
);

-- Indexes for high-speed temporal & filter queries
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry(timestamp);
CREATE INDEX IF NOT EXISTS idx_telemetry_signal ON telemetry(signal_name);
CREATE INDEX IF NOT EXISTS idx_telemetry_sig_time ON telemetry(signal_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON vehicle_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON vehicle_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_severity ON vehicle_events(severity);
CREATE INDEX IF NOT EXISTS idx_diag_timestamp ON diagnostic_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_diag_dtc ON diagnostic_logs(dtc_code);
"""


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection with row factories and WAL mode."""
    target_path = Path(db_path) if db_path else DB_ABSOLUTE_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        timeout=30.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    # Configure WAL mode and foreign keys for high read-concurrency on edge devices
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_db(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for safe database transactions."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    """Initialize database tables and indexes."""
    with get_db(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


def reset_db(db_path: Path | str | None = None) -> None:
    """Clear all records from database tables while preserving schema."""
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM telemetry;")
        conn.execute("DELETE FROM vehicle_events;")
        conn.execute("DELETE FROM diagnostic_logs;")
        conn.execute("DELETE FROM ingestion_audit;")
        conn.commit()
