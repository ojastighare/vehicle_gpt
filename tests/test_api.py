"""Integration tests for FastAPI endpoints, request validation, and error handling."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_api_health():
    """Verify GET /api/health returns 200 with database and offline mode status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["read_only_safety_mode"] is True
    assert data["database"]["telemetry_records"] > 0


def test_api_vehicle_summary():
    """Verify GET /api/vehicle/summary returns valid vehicle snapshot data."""
    res = client.get("/api/vehicle/summary")
    assert res.status_code == 200
    data = res.json()
    assert "battery_soc_pct" in data
    assert "driving_range_km" in data
    assert "operating_status" in data


def test_api_telemetry_query():
    """Verify GET /api/telemetry with parameter filtering."""
    res = client.get("/api/telemetry?signal_name=battery_temperature&limit=50")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    assert data["records"][0]["signal_name"] == "battery_temperature"


def test_api_events_query():
    """Verify GET /api/events with event type filter."""
    res = client.get("/api/events?event_type=ADAS_DISENGAGEMENT&limit=20")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    assert data["events"][0]["event_type"] == "ADAS_DISENGAGEMENT"


def test_api_natural_language_query_endpoint():
    """Verify POST /api/query processes question and returns structured evidence."""
    payload = {
        "question": "What happened before the battery overheating warning?",
        "use_llm": False,
    }
    res = client.post("/api/query", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "WARNING_CORRELATION"
    assert "Preceding Analysis for Diagnostic Warning" in data["answer"]
    assert len(data["evidence"]) > 0
    assert data["model_used"] == "deterministic-engine"
    assert data["latency"]["total_ms"] > 0


def test_api_query_validation_error():
    """Verify input validation rejects empty or too short questions."""
    payload = {"question": "a"}  # min_length is 2
    res = client.post("/api/query", json=payload)
    assert res.status_code == 422


def test_api_system_metrics():
    """Verify GET /api/metrics exposes memory footprint and edge specifications."""
    res = client.get("/api/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["memory_rss_mb"] > 0
    assert data["total_telemetry_records"] > 0
    assert "2GB RAM" in data["edge_target_compatibility"]
