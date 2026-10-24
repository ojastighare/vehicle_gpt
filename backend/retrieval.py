"""Database retrieval layer with parameterized queries, pagination, and time filters."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from backend.database import get_db
from backend.schemas import EvidenceRecord, VehicleSummary


class VehicleDataRetriever:
    """Provides optimized, parameterized SQL queries for telemetry, events, and diagnostics."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path

    def get_latest_telemetry(self, signal_name: str) -> Optional[dict[str, Any]]:
        """Retrieve the most recent reading for a given signal."""
        with get_db(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT timestamp, signal_name, value, unit, source
                   FROM telemetry
                   WHERE signal_name = ?
                   ORDER BY timestamp DESC
                   LIMIT 1;""",
                (signal_name,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_telemetry_series(
        self,
        signal_name: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Fetch chronological telemetry series within an optional time range."""
        query = "SELECT timestamp, signal_name, value, unit, source FROM telemetry WHERE signal_name = ?"
        params: list[Any] = [signal_name]

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp ASC LIMIT ?;"
        params.append(limit)

        with get_db(self.db_path) as conn:
            cursor = conn.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def get_events(
        self,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Retrieve vehicle events filtered by type, severity, and time bounds."""
        query = "SELECT id, timestamp, event_type, severity, description, source, metadata FROM vehicle_events WHERE 1=1"
        params: list[Any] = []

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp DESC LIMIT ?;"
        params.append(limit)

        with get_db(self.db_path) as conn:
            cursor = conn.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def get_events_around_timestamp(
        self,
        center_timestamp: str,
        minutes_before: int = 30,
        minutes_after: int = 15,
    ) -> list[dict[str, Any]]:
        """Fetch all events in a window before and after a specific timestamp."""
        center_dt = datetime.fromisoformat(center_timestamp.replace("Z", "+00:00"))
        start_dt = (center_dt - timedelta(minutes=minutes_before)).isoformat()
        end_dt = (center_dt + timedelta(minutes=minutes_after)).isoformat()

        query = """SELECT id, timestamp, event_type, severity, description, source, metadata
                   FROM vehicle_events
                   WHERE timestamp >= ? AND timestamp <= ?
                   ORDER BY timestamp ASC;"""

        with get_db(self.db_path) as conn:
            cursor = conn.execute(query, (start_dt, end_dt))
            return [dict(r) for r in cursor.fetchall()]

    def get_telemetry_around_timestamp(
        self,
        center_timestamp: str,
        signal_names: list[str],
        minutes_before: int = 30,
        minutes_after: int = 10,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch time-correlated telemetry before and after an event timestamp."""
        center_dt = datetime.fromisoformat(center_timestamp.replace("Z", "+00:00"))
        start_dt = (center_dt - timedelta(minutes=minutes_before)).isoformat()
        end_dt = (center_dt + timedelta(minutes=minutes_after)).isoformat()

        results: dict[str, list[dict[str, Any]]] = {sig: [] for sig in signal_names}

        for sig in signal_names:
            query = """SELECT timestamp, signal_name, value, unit, source
                       FROM telemetry
                       WHERE signal_name = ? AND timestamp >= ? AND timestamp <= ?
                       ORDER BY timestamp ASC;"""
            with get_db(self.db_path) as conn:
                cursor = conn.execute(query, (sig, start_dt, end_dt))
                results[sig] = [dict(r) for r in cursor.fetchall()]

        return results

    def get_diagnostic_logs(
        self,
        dtc_code: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve diagnostic DTC trouble code logs."""
        query = "SELECT id, timestamp, dtc_code, ecu, status, description FROM diagnostic_logs WHERE 1=1"
        params: list[Any] = []

        if dtc_code:
            query += " AND dtc_code = ?"
            params.append(dtc_code)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp DESC LIMIT ?;"
        params.append(limit)

        with get_db(self.db_path) as conn:
            cursor = conn.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def get_vehicle_summary(self) -> VehicleSummary:
        """Compute latest snapshot vehicle summary for dashboard header cards."""
        with get_db(self.db_path) as conn:
            # Latest timestamp across telemetry
            t_row = conn.execute("SELECT MAX(timestamp) as latest_ts FROM telemetry;").fetchone()
            latest_ts = t_row["latest_ts"] if t_row and t_row["latest_ts"] else None

            # Get latest for key signals
            def _get_val(sig: str, default: float = 0.0) -> float:
                r = conn.execute(
                    "SELECT value FROM telemetry WHERE signal_name = ? ORDER BY timestamp DESC LIMIT 1;",
                    (sig,),
                ).fetchone()
                return float(r["value"]) if r else default

            speed = _get_val("vehicle_speed", 0.0)
            soc = _get_val("state_of_charge", 85.0)
            batt_temp = _get_val("battery_temperature", 24.0)
            driving_range = _get_val("driving_range", 360.0)
            energy_cons = _get_val("energy_consumption", 16.2)

            # Warnings count
            crit_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM vehicle_events WHERE severity = 'CRITICAL';"
            ).fetchone()
            crit_count = crit_row["cnt"] if crit_row else 0

            # ADAS disengagements in last 24h of data
            adas_cnt = 0
            if latest_ts:
                latest_dt = datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))
                day_prior = (latest_dt - timedelta(days=1)).isoformat()
                adas_row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM vehicle_events
                       WHERE event_type = 'ADAS_DISENGAGEMENT' AND timestamp >= ?;""",
                    (day_prior,),
                ).fetchone()
                adas_cnt = adas_row["cnt"] if adas_row else 0

            dtc_row = conn.execute("SELECT COUNT(*) as cnt FROM diagnostic_logs;").fetchone()
            dtc_cnt = dtc_row["cnt"] if dtc_row else 0

            return VehicleSummary(
                latest_timestamp=latest_ts,
                current_speed_kmh=speed,
                battery_soc_pct=soc,
                battery_temp_c=batt_temp,
                driving_range_km=driving_range,
                energy_consumption_kwh=energy_cons,
                total_distance_km=14200.0,
                critical_warnings_count=crit_count,
                adas_disengagements_24h=adas_cnt,
                active_dtc_count=dtc_cnt,
                operating_status="ATTENTION" if crit_count > 0 else "NORMAL",
            )
