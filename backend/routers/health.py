"""Health check and embedded metrics router for VehicleGPT."""

import os
import resource
from fastapi import APIRouter
from backend.config import DB_ABSOLUTE_PATH, settings
from backend.database import get_db
from backend.llm_service import local_llm_service
from backend.schemas import SystemMetrics

router = APIRouter(prefix="/api", tags=["Health & System"])


@router.get("/health")
async def health_check():
    """Application and dependency health verification."""
    ollama_status = await local_llm_service.check_health()
    db_ok = False
    telemetry_count = 0
    events_count = 0

    try:
        with get_db() as conn:
            t_row = conn.execute("SELECT COUNT(*) as cnt FROM telemetry;").fetchone()
            e_row = conn.execute("SELECT COUNT(*) as cnt FROM vehicle_events;").fetchone()
            telemetry_count = t_row["cnt"] if t_row else 0
            events_count = e_row["cnt"] if e_row else 0
            db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": {
            "status": "connected" if db_ok else "error",
            "path": str(DB_ABSOLUTE_PATH),
            "telemetry_records": telemetry_count,
            "event_records": events_count,
        },
        "ai_engine": {
            "mode": "offline-deterministic" if not settings.USE_LOCAL_LLM else "local-slm",
            "ollama_available": ollama_status["available"],
            "configured_model": settings.OLLAMA_MODEL,
            "model_installed": ollama_status.get("model_installed", False),
        },
        "environment": settings.ENVIRONMENT,
        "read_only_safety_mode": True,
    }


@router.get("/metrics", response_model=SystemMetrics)
async def system_metrics():
    """Expose edge memory footprint and record counts for performance benchmarking."""
    # Peak memory usage in MB (macOS returns bytes for ru_maxrss, Linux returns KB)
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    # On macOS, ru_maxrss is in bytes
    rss_mb = round(rusage.ru_maxrss / (1024 * 1024), 2)

    t_cnt, e_cnt, d_cnt = 0, 0, 0
    db_size_kb = 0.0

    if DB_ABSOLUTE_PATH.exists():
        db_size_kb = round(os.path.getsize(DB_ABSOLUTE_PATH) / 1024.0, 1)

    try:
        with get_db() as conn:
            t_cnt = conn.execute("SELECT COUNT(*) FROM telemetry;").fetchone()[0]
            e_cnt = conn.execute("SELECT COUNT(*) FROM vehicle_events;").fetchone()[0]
            d_cnt = conn.execute("SELECT COUNT(*) FROM diagnostic_logs;").fetchone()[0]
    except Exception:
        pass

    ollama_info = await local_llm_service.check_health()

    return SystemMetrics(
        memory_rss_mb=rss_mb,
        total_telemetry_records=t_cnt,
        total_event_records=e_cnt,
        total_diagnostic_records=d_cnt,
        database_size_kb=db_size_kb,
        ollama_connected=ollama_info["available"],
        configured_model=settings.OLLAMA_MODEL,
        edge_target_compatibility="Target: ~2GB RAM, 2 ARM A5X Cores, < 2.0s latency",
    )
