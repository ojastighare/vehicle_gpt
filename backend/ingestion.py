"""Data ingestion, normalization, and provenance auditing pipeline for VehicleGPT."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from dateutil import parser as date_parser

from backend.database import get_db
from backend.schemas import RawIngestionPayload, TelemetryItem, VehicleEventItem

SIGNAL_NORMALIZATION_MAP = {
    "speed": "vehicle_speed",
    "velocity": "vehicle_speed",
    "vehicle_speed": "vehicle_speed",
    "batt_temp": "battery_temperature",
    "battery_temp": "battery_temperature",
    "battery_temperature": "battery_temperature",
    "pack_temp": "battery_temperature",
    "soc": "state_of_charge",
    "state_of_charge": "state_of_charge",
    "battery_level": "state_of_charge",
    "consumption": "energy_consumption",
    "energy_consumption": "energy_consumption",
    "efficiency": "energy_consumption",
    "range": "driving_range",
    "driving_range": "driving_range",
    "estimated_range": "driving_range",
    "ambient_temp": "ambient_temperature",
    "ambient_temperature": "ambient_temperature",
}

UNIT_NORMALIZATION_MAP = {
    "km/h": ("km/h", lambda v: v),
    "kph": ("km/h", lambda v: v),
    "mph": ("km/h", lambda v: round(v * 1.60934, 1)),
    "°c": ("°C", lambda v: v),
    "c": ("°C", lambda v: v),
    "degc": ("°C", lambda v: v),
    "°f": ("°C", lambda v: round((v - 32) * 5.0 / 9.0, 1)),
    "f": ("°C", lambda v: round((v - 32) * 5.0 / 9.0, 1)),
    "%": ("%", lambda v: v),
    "percent": ("%", lambda v: v),
    "kwh/100 km": ("kWh/100 km", lambda v: v),
    "kwh/100km": ("kWh/100 km", lambda v: v),
    "wh/km": ("kWh/100 km", lambda v: round(v / 10.0, 1)),
    "km": ("km", lambda v: v),
    "miles": ("km", lambda v: round(v * 1.60934, 1)),
    "mi": ("km", lambda v: round(v * 1.60934, 1)),
}

DEFAULT_SIGNAL_UNITS = {
    "vehicle_speed": "km/h",
    "battery_temperature": "°C",
    "state_of_charge": "%",
    "energy_consumption": "kWh/100 km",
    "driving_range": "km",
    "ambient_temperature": "°C",
}


class IngestionPipeline:
    """Validates, normalizes, and stores vehicle telemetry and events."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path

    def normalize_timestamp(self, ts_input: Any) -> str:
        """Parse arbitrary timestamps into standard ISO 8601 UTC strings."""
        if isinstance(ts_input, datetime):
            if ts_input.tzinfo is None:
                ts_input = ts_input.replace(tzinfo=timezone.utc)
            return ts_input.astimezone(timezone.utc).isoformat()

        if isinstance(ts_input, (int, float)):
            # Epoch timestamp handling
            return datetime.fromtimestamp(ts_input, tz=timezone.utc).isoformat()

        # Parse string
        dt = date_parser.parse(str(ts_input))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    def ingest_record(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Ingest a single record with validation and normalization."""
        try:
            # Audit payload initially
            ts_str = self.normalize_timestamp(raw_data.get("timestamp"))

            # Determine whether this is a telemetry signal or a vehicle event
            signal_key = raw_data.get("signal") or raw_data.get("signal_name") or raw_data.get("name")
            event_type = raw_data.get("event_type")

            if signal_key:
                norm_sig = SIGNAL_NORMALIZATION_MAP.get(str(signal_key).lower().strip(), str(signal_key).lower().strip())
                val = float(raw_data["value"])
                raw_unit = str(raw_data.get("unit", "")).strip().lower()

                if raw_unit in UNIT_NORMALIZATION_MAP:
                    norm_unit, conv_func = UNIT_NORMALIZATION_MAP[raw_unit]
                    norm_val = conv_func(val)
                else:
                    norm_unit = DEFAULT_SIGNAL_UNITS.get(norm_sig, raw_unit or "unitless")
                    norm_val = val

                source = raw_data.get("source", "INGESTION_SERVICE")

                # Validate with Pydantic
                item = TelemetryItem(
                    timestamp=ts_str,
                    signal_name=norm_sig,
                    value=norm_val,
                    unit=norm_unit,
                    source=source,
                )

                with get_db(self.db_path) as conn:
                    # Check for exact duplicate
                    cursor = conn.execute(
                        "SELECT id FROM telemetry WHERE timestamp = ? AND signal_name = ? LIMIT 1;",
                        (item.timestamp, item.signal_name),
                    )
                    if cursor.fetchone():
                        self._log_audit(conn, ts_str, "DUPLICATE_IGNORED", "Duplicate telemetry record dropped", raw_data)
                        return {"status": "DUPLICATE", "type": "telemetry"}

                    conn.execute(
                        """INSERT INTO telemetry (timestamp, signal_name, value, unit, source)
                           VALUES (?, ?, ?, ?, ?);""",
                        (item.timestamp, item.signal_name, item.value, item.unit, item.source),
                    )

                return {"status": "SUCCESS", "type": "telemetry", "signal": norm_sig, "value": norm_val}

            elif event_type:
                norm_event = str(event_type).upper().strip()
                desc = raw_data.get("description", "Vehicle event occurred")
                sev = raw_data.get("severity", "INFO").upper()
                source = raw_data.get("source", "EVENT_SERVICE")
                meta = raw_data.get("metadata")
                if isinstance(meta, dict):
                    meta = json.dumps(meta)

                item = VehicleEventItem(
                    timestamp=ts_str,
                    event_type=norm_event,
                    severity=sev,
                    description=desc,
                    source=source,
                    metadata=meta,
                )

                with get_db(self.db_path) as conn:
                    cursor = conn.execute(
                        "SELECT id FROM vehicle_events WHERE timestamp = ? AND event_type = ? AND description = ? LIMIT 1;",
                        (item.timestamp, item.event_type, item.description),
                    )
                    if cursor.fetchone():
                        self._log_audit(conn, ts_str, "DUPLICATE_IGNORED", "Duplicate event record dropped", raw_data)
                        return {"status": "DUPLICATE", "type": "event"}

                    conn.execute(
                        """INSERT INTO vehicle_events (timestamp, event_type, severity, description, source, metadata)
                           VALUES (?, ?, ?, ?, ?, ?);""",
                        (item.timestamp, item.event_type, item.severity, item.description, item.source, item.metadata),
                    )

                return {"status": "SUCCESS", "type": "event", "event_type": norm_event}

            else:
                with get_db(self.db_path) as conn:
                    self._log_audit(conn, ts_str, "REJECTED", "Payload missing signal_name or event_type", raw_data)
                return {"status": "REJECTED", "error": "Missing signal or event_type"}

        except Exception as e:
            with get_db(self.db_path) as conn:
                self._log_audit(conn, datetime.now(timezone.utc).isoformat(), "REJECTED", str(e), raw_data)
            return {"status": "ERROR", "error": str(e)}

    def ingest_batch(self, dataset: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        """Fast bulk ingestion with transaction optimization for simulator and file loads."""
        telemetry_rows = []
        event_rows = []
        diag_rows = []

        # Process telemetry
        for t in dataset.get("telemetry", []):
            try:
                ts = self.normalize_timestamp(t["timestamp"])
                sig = SIGNAL_NORMALIZATION_MAP.get(str(t["signal_name"]).lower().strip(), str(t["signal_name"]))
                val = float(t["value"])
                unit = t.get("unit") or DEFAULT_SIGNAL_UNITS.get(sig, "")
                src = t.get("source", "SIMULATOR")
                telemetry_rows.append((ts, sig, val, unit, src))
            except Exception:
                continue

        # Process events
        for e in dataset.get("events", []):
            try:
                ts = self.normalize_timestamp(e["timestamp"])
                e_type = str(e["event_type"]).upper().strip()
                sev = str(e.get("severity", "INFO")).upper().strip()
                desc = e.get("description", "")
                src = e.get("source", "SIMULATOR")
                meta = e.get("metadata")
                if isinstance(meta, dict):
                    meta = json.dumps(meta)
                event_rows.append((ts, e_type, sev, desc, src, meta))
            except Exception:
                continue

        # Process diagnostics
        for d in dataset.get("diagnostics", []):
            try:
                ts = self.normalize_timestamp(d["timestamp"])
                dtc = str(d["dtc_code"]).strip()
                ecu = str(d.get("ecu", "VCU")).strip()
                status = str(d.get("status", "CONFIRMED")).strip()
                desc = d.get("description", "")
                diag_rows.append((ts, dtc, ecu, status, desc))
            except Exception:
                continue

        with get_db(self.db_path) as conn:
            if telemetry_rows:
                conn.executemany(
                    "INSERT INTO telemetry (timestamp, signal_name, value, unit, source) VALUES (?, ?, ?, ?, ?);",
                    telemetry_rows,
                )
            if event_rows:
                conn.executemany(
                    "INSERT INTO vehicle_events (timestamp, event_type, severity, description, source, metadata) VALUES (?, ?, ?, ?, ?, ?);",
                    event_rows,
                )
            if diag_rows:
                conn.executemany(
                    "INSERT INTO diagnostic_logs (timestamp, dtc_code, ecu, status, description) VALUES (?, ?, ?, ?, ?);",
                    diag_rows,
                )

        return {
            "telemetry_count": len(telemetry_rows),
            "event_count": len(event_rows),
            "diagnostic_count": len(diag_rows),
        }

    def _log_audit(self, conn: Any, ts: str, status: str, reason: str, payload: Any) -> None:
        """Record data quality anomaly or rejection in audit log."""
        try:
            conn.execute(
                "INSERT INTO ingestion_audit (timestamp, status, reason, raw_payload) VALUES (?, ?, ?, ?);",
                (ts, status, reason, json.dumps(payload, default=str)),
            )
        except Exception:
            pass
