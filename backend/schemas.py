"""Pydantic models and schemas for data validation, ingestion, and API responses."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class TelemetryItem(BaseModel):
    id: Optional[int] = None
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    signal_name: str = Field(..., description="Normalized signal identifier")
    value: float = Field(..., description="Numerical telemetry value")
    unit: str = Field(..., description="Engineering measurement unit")
    source: str = Field(default="SIMULATOR", description="Bus or subsystem origin")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        try:
            # Validate ISO 8601 formatting
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except Exception as e:
            raise ValueError(f"Invalid timestamp format: {v}. Must be ISO 8601.") from e


class VehicleEventItem(BaseModel):
    id: Optional[int] = None
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    event_type: str = Field(..., description="Categorical event type")
    severity: str = Field(default="INFO", description="INFO, WARNING, or CRITICAL")
    description: str = Field(..., description="Event explanation")
    source: str = Field(default="SIMULATOR", description="Originating subsystem")
    metadata: Optional[str] = Field(default=None, description="Supplementary JSON context")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        allowed = {"INFO", "WARNING", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in allowed:
            raise ValueError(f"Severity must be one of {allowed}, got: {v}")
        return upper_v


class DiagnosticLogItem(BaseModel):
    id: Optional[int] = None
    timestamp: str
    dtc_code: str
    ecu: str
    status: str = "CONFIRMED"
    description: str


class RawIngestionPayload(BaseModel):
    """Raw record for ingestion validation and normalization."""
    timestamp: str
    name: Optional[str] = None
    signal: Optional[str] = None
    event_type: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    severity: Optional[str] = "INFO"
    description: Optional[str] = None
    source: Optional[str] = "INGESTION_SERVICE"
    metadata: Optional[dict[str, Any] | str] = None


class EvidenceRecord(BaseModel):
    timestamp: str
    record_type: str  # "telemetry" or "event" or "diagnostic"
    label: str
    value: Optional[float] = None
    unit: Optional[str] = None
    severity: Optional[str] = None
    source: Optional[str] = None
    details: Optional[str] = None


class LatencyBreakdown(BaseModel):
    retrieval_ms: float = 0.0
    analytics_ms: float = 0.0
    llm_ms: float = 0.0
    total_ms: float = 0.0


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500, description="Natural language question")
    use_llm: Optional[bool] = Field(default=False, description="Whether to request local SLM synthesis")
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class QueryResponse(BaseModel):
    question: str
    intent: str
    answer: str
    evidence: list[EvidenceRecord] = []
    summary_stats: dict[str, Any] = {}
    time_window: dict[str, Optional[str]] = {}
    model_used: str = "deterministic-engine"
    latency: LatencyBreakdown
    confidence: str = "HIGH"  # HIGH, MEDIUM, LOW, INSUFFICIENT_EVIDENCE
    clarification_prompt: Optional[str] = None
    disclaimer: str = (
        "VehicleGPT is a diagnostic assistance prototype utilizing simulated data. "
        "It does not issue vehicle commands and is not a substitute for certified automotive diagnostics."
    )


class VehicleSummary(BaseModel):
    latest_timestamp: Optional[str] = None
    current_speed_kmh: float = 0.0
    battery_soc_pct: float = 0.0
    battery_temp_c: float = 0.0
    driving_range_km: float = 0.0
    energy_consumption_kwh: float = 0.0
    total_distance_km: float = 0.0
    critical_warnings_count: int = 0
    adas_disengagements_24h: int = 0
    active_dtc_count: int = 0
    operating_status: str = "NORMAL"


class SystemMetrics(BaseModel):
    memory_rss_mb: float
    total_telemetry_records: int
    total_event_records: int
    total_diagnostic_records: int
    database_size_kb: float
    ollama_connected: bool
    configured_model: str
    edge_target_compatibility: str = "~2GB RAM, 2 ARM A5X Cores target specification"
