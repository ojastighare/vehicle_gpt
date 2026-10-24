"""Unit tests for deterministic calculations, trends, surges, and event correlation."""

import pytest
from backend.analytics import VehicleAnalytics


def test_summary_statistics_calculation():
    """Verify min, max, mean, median, and std_dev computations."""
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    stats = VehicleAnalytics.compute_summary_stats(data)
    assert stats["count"] == 5
    assert stats["min"] == 10.0
    assert stats["max"] == 50.0
    assert stats["mean"] == 30.0
    assert stats["median"] == 30.0
    assert stats["std_dev"] == 14.14


def test_driving_range_trend_analysis():
    """Verify range reduction percentage and delta computation."""
    records = [
        {"timestamp": f"2026-10-0{i}T10:00:00Z", "value": 400.0 - (i * 10), "unit": "km", "source": "VCU"}
        for i in range(1, 9)
    ]
    res = VehicleAnalytics.analyze_driving_range_trend(records)
    assert res["status"] == "VALID"
    assert res["first_reading"] == 390.0
    assert res["latest_reading"] == 320.0
    assert res["percentage_change"] < 0
    assert len(res["evidence"]) == 2


def test_energy_consumption_surge_detection():
    """Verify peak energy consumption identification and threshold exceedance."""
    records = [
        {"timestamp": "2026-10-15T12:00:00Z", "value": 16.5, "unit": "kWh/100 km"},
        {"timestamp": "2026-10-16T12:00:00Z", "value": 18.2, "unit": "kWh/100 km"},
        {"timestamp": "2026-10-18T14:30:00Z", "value": 35.4, "unit": "kWh/100 km"},
        {"timestamp": "2026-10-19T12:00:00Z", "value": 17.0, "unit": "kWh/100 km"},
    ]
    res = VehicleAnalytics.detect_consumption_surges(records, threshold=25.0)
    assert res["peak_value"] == 35.4
    assert res["peak_timestamp"] == "2026-10-18T14:30:00Z"
    assert res["anomaly_count"] == 1


def test_city_vs_highway_comparison():
    """Verify city vs highway consumption calculation."""
    speed_recs = [
        {"timestamp": "2026-10-20T08:00:00Z", "value": 30.0},
        {"timestamp": "2026-10-20T08:10:00Z", "value": 40.0},
        {"timestamp": "2026-10-20T17:00:00Z", "value": 100.0},
        {"timestamp": "2026-10-20T17:10:00Z", "value": 110.0},
    ]
    cons_recs = [
        {"timestamp": "2026-10-20T08:00:00Z", "value": 15.0},
        {"timestamp": "2026-10-20T08:10:00Z", "value": 16.0},
        {"timestamp": "2026-10-20T17:00:00Z", "value": 22.0},
        {"timestamp": "2026-10-20T17:10:00Z", "value": 24.0},
    ]
    res = VehicleAnalytics.compare_city_vs_highway(speed_recs, cons_recs)
    assert res["city_stats"]["mean"] == 15.5
    assert res["highway_stats"]["mean"] == 23.0
    assert res["highway_vs_city_consumption_delta"] == 7.5
