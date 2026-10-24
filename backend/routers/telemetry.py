"""Telemetry data and signal trend query endpoints."""

from typing import Optional
from fastapi import APIRouter, Query
from backend.analytics import VehicleAnalytics
from backend.retrieval import VehicleDataRetriever
from backend.schemas import VehicleSummary

router = APIRouter(prefix="/api", tags=["Telemetry & Status"])
retriever = VehicleDataRetriever()


@router.get("/vehicle/summary", response_model=VehicleSummary)
async def get_vehicle_summary():
    """Retrieve current operational status and snapshot telemetry for dashboard cards."""
    return retriever.get_vehicle_summary()


@router.get("/telemetry")
async def get_telemetry(
    signal_name: Optional[str] = Query(None, description="Signal identifier (e.g. battery_temperature)"),
    start_time: Optional[str] = Query(None, description="ISO 8601 start timestamp"),
    end_time: Optional[str] = Query(None, description="ISO 8601 end timestamp"),
    limit: int = Query(200, ge=1, le=2000, description="Maximum records to return"),
):
    """Query telemetry records with optional signal and temporal filtering."""
    if signal_name:
        records = retriever.get_telemetry_series(
            signal_name=signal_name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    else:
        # Default to a mix of battery_temperature and energy_consumption if no signal specified
        records = retriever.get_telemetry_series("battery_temperature", limit=limit // 2)
        records += retriever.get_telemetry_series("energy_consumption", limit=limit // 2)
        records.sort(key=lambda x: x["timestamp"], reverse=True)

    return {"count": len(records), "records": records}


@router.get("/trends")
async def get_signal_trends(
    signal_name: str = Query(..., description="Signal to analyze, e.g. battery_temperature, energy_consumption"),
    start_time: Optional[str] = Query(None, description="ISO 8601 start timestamp"),
    end_time: Optional[str] = Query(None, description="ISO 8601 end timestamp"),
    limit: int = Query(500, ge=10, le=2000),
):
    """Retrieve calculated trends, statistical aggregates, and downsampled chart data."""
    series = retriever.get_telemetry_series(
        signal_name=signal_name,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    values = [r["value"] for r in series]
    stats = VehicleAnalytics.compute_summary_stats(values)

    return {
        "signal_name": signal_name,
        "sample_count": len(series),
        "statistics": stats,
        "time_bounds": {
            "start": series[0]["timestamp"] if series else None,
            "end": series[-1]["timestamp"] if series else None,
        },
        "series": series,
    }
