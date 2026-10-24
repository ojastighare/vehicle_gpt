"""Unit tests for data validation, normalization, and ingestion pipeline."""

import pytest
from pathlib import Path
from backend.database import get_db, init_db
from backend.ingestion import IngestionPipeline


@pytest.fixture
def test_pipeline(tmp_path: Path):
    db_file = tmp_path / "test_ingestion.db"
    init_db(db_file)
    return IngestionPipeline(db_file)


def test_telemetry_normalization_and_unit_conversion(test_pipeline: IngestionPipeline):
    """Verify signal alias normalization and engineering unit conversions."""
    # Imperial speed (mph -> km/h)
    rec1 = {
        "timestamp": "2026-10-22T08:00:00Z",
        "signal": "speed",
        "value": 60.0,
        "unit": "mph",
        "source": "CAN_BUS",
    }
    res1 = test_pipeline.ingest_record(rec1)
    assert res1["status"] == "SUCCESS"
    assert res1["signal"] == "vehicle_speed"
    assert round(res1["value"], 1) == 96.6  # 60 * 1.60934

    # Fahrenheit to Celsius
    rec2 = {
        "timestamp": "2026-10-22T08:05:00Z",
        "signal": "battery_temp",
        "value": 104.0,
        "unit": "°F",
        "source": "BMS_HAL",
    }
    res2 = test_pipeline.ingest_record(rec2)
    assert res2["status"] == "SUCCESS"
    assert res2["signal"] == "battery_temperature"
    assert round(res2["value"], 1) == 40.0  # (104 - 32) * 5/9


def test_duplicate_record_handling(test_pipeline: IngestionPipeline):
    """Ensure duplicate records with the exact timestamp and signal are dropped cleanly."""
    rec = {
        "timestamp": "2026-10-22T09:00:00Z",
        "signal_name": "vehicle_speed",
        "value": 45.0,
        "unit": "km/h",
    }
    res_first = test_pipeline.ingest_record(rec)
    assert res_first["status"] == "SUCCESS"

    res_second = test_pipeline.ingest_record(rec)
    assert res_second["status"] == "DUPLICATE"

    # Verify only 1 entry in DB
    with get_db(test_pipeline.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM telemetry WHERE timestamp = '2026-10-22T09:00:00+00:00';").fetchone()[0]
        assert count == 1


def test_invalid_payload_rejection_and_audit(test_pipeline: IngestionPipeline):
    """Ensure invalid payloads missing required attributes are rejected and audited."""
    invalid_rec = {
        "timestamp": "not-a-valid-date",
        "value": 10.0,
    }
    res = test_pipeline.ingest_record(invalid_rec)
    assert res["status"] in ("ERROR", "REJECTED")

    with get_db(test_pipeline.db_path) as conn:
        audit_count = conn.execute("SELECT COUNT(*) FROM ingestion_audit WHERE status = 'REJECTED';").fetchone()[0]
        assert audit_count >= 1
