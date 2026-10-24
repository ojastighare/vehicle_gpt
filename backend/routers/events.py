"""Vehicle events and diagnostic trouble codes query router."""

from typing import Optional
from fastapi import APIRouter, Query
from backend.retrieval import VehicleDataRetriever

router = APIRouter(prefix="/api", tags=["Events & Diagnostics"])
retriever = VehicleDataRetriever()


@router.get("/events")
async def get_events(
    event_type: Optional[str] = Query(None, description="Event type (e.g. ADAS_DISENGAGEMENT, DIAGNOSTIC_WARNING)"),
    severity: Optional[str] = Query(None, description="Severity (INFO, WARNING, CRITICAL)"),
    start_time: Optional[str] = Query(None, description="ISO 8601 start timestamp"),
    end_time: Optional[str] = Query(None, description="ISO 8601 end timestamp"),
    limit: int = Query(100, ge=1, le=500),
):
    """Retrieve vehicle events timeline with multi-criteria filtering."""
    events = retriever.get_events(
        event_type=event_type,
        severity=severity,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    return {"count": len(events), "events": events}


@router.get("/diagnostics")
async def get_diagnostics(
    dtc_code: Optional[str] = Query(None, description="DTC trouble code, e.g. DTC_BMS_TEMP_HIGH"),
    start_time: Optional[str] = Query(None, description="ISO 8601 start timestamp"),
    end_time: Optional[str] = Query(None, description="ISO 8601 end timestamp"),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve diagnostic trouble code (DTC) history."""
    logs = retriever.get_diagnostic_logs(
        dtc_code=dtc_code,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    return {"count": len(logs), "diagnostics": logs}
