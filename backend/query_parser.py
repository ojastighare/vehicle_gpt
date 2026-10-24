"""Natural-language query parser with intent classification and temporal extraction."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from dateutil import parser as date_parser


class ParsedQuery:
    """Structured representation of a user query."""

    def __init__(
        self,
        raw_question: str,
        intent: str,
        time_window: dict[str, Optional[str]],
        entities: dict[str, Any],
        is_supported: bool = True,
        clarification_note: Optional[str] = None,
    ):
        self.raw_question = raw_question
        self.intent = intent
        self.time_window = time_window
        self.entities = entities
        self.is_supported = is_supported
        self.clarification_note = clarification_note


class QueryParser:
    """Deterministic rule-and-pattern query intent parser."""

    def __init__(self, anchor_time: Optional[datetime] = None):
        # Anchor time representing the current simulated vehicle clock
        self.anchor_time = anchor_time or datetime(2026, 10, 22, 14, 0, 0, tzinfo=timezone.utc)

    def parse(self, question: str, user_start: Optional[str] = None, user_end: Optional[str] = None) -> ParsedQuery:
        q_clean = question.strip()
        q_lower = q_clean.lower()

        # Step 1: Temporal extraction
        time_window = self._extract_time_window(q_lower, user_start, user_end)

        # Step 2: Intent classification via deterministic matching
        clarification = None

        # 1. ADAS Disengagement
        if any(w in q_lower for w in ["adas", "autopilot", "lane keep", "steering disengage", "disengagement"]):
            intent = "ADAS_DISENGAGEMENTS"
            entities = {"event_type": "ADAS_DISENGAGEMENT"}
            if not time_window.get("start") and "yesterday" not in q_lower:
                # Default to last 7 days if no window specified
                time_window = {
                    "start": (self.anchor_time - timedelta(days=7)).isoformat(),
                    "end": self.anchor_time.isoformat(),
                    "label": "past 7 days (default applied)",
                }
                clarification = "No explicit date specified; showing ADAS events from the past 7 days."

        # 2. Warning Precedents & Correlation ("What happened before...")
        elif (
            ("what happened before" in q_lower or "events before" in q_lower or "prior to" in q_lower or "preceding" in q_lower)
            and ("warning" in q_lower or "overheating" in q_lower or "alert" in q_lower or "dtc" in q_lower)
        ):
            intent = "WARNING_CORRELATION"
            target = "overheating" if "overheat" in q_lower or "battery" in q_lower else "any_critical"
            entities = {"warning_target": target, "window_minutes_before": 30}

        # 3. Driving Range Reduction ("Why has my driving range reduced over the last two weeks?")
        elif (
            ("range" in q_lower and ("reduced" in q_lower or "drop" in q_lower or "decreased" in q_lower or "lower" in q_lower or "why" in q_lower))
            or ("driving range" in q_lower and "two weeks" in q_lower)
        ):
            intent = "DRIVING_RANGE_ANALYSIS"
            entities = {"signal_name": "driving_range", "correlated_signals": ["ambient_temperature", "energy_consumption"]}
            if not time_window.get("start"):
                time_window = {
                    "start": (self.anchor_time - timedelta(days=14)).isoformat(),
                    "end": self.anchor_time.isoformat(),
                    "label": "last two weeks",
                }

        # 4. Energy Consumption Surge / Drop in efficiency
        elif (
            ("energy" in q_lower or "consumption" in q_lower or "fuel efficiency" in q_lower or "efficiency" in q_lower)
            and ("increase" in q_lower or "surge" in q_lower or "drop" in q_lower or "largest" in q_lower or "highest" in q_lower or "spike" in q_lower or "unusually high" in q_lower)
        ):
            intent = "ENERGY_CONSUMPTION_SURGE"
            entities = {"signal_name": "energy_consumption"}
            if not time_window.get("start"):
                time_window = {
                    "start": (self.anchor_time - timedelta(days=21)).isoformat(),
                    "end": self.anchor_time.isoformat(),
                    "label": "all recorded history",
                }

        # 5. City vs Highway Comparison
        elif ("city" in q_lower and "highway" in q_lower) or ("compare" in q_lower and "driving" in q_lower):
            intent = "CITY_VS_HIGHWAY_COMPARISON"
            entities = {"signals": ["energy_consumption", "vehicle_speed"]}

        # 6. Battery Temperature Trend
        elif "battery" in q_lower and ("temperature" in q_lower or "temp" in q_lower):
            intent = "BATTERY_TEMPERATURE_TREND"
            entities = {"signal_name": "battery_temperature"}
            if not time_window.get("start"):
                time_window = {
                    "start": (self.anchor_time - timedelta(days=7)).isoformat(),
                    "end": self.anchor_time.isoformat(),
                    "label": "last 7 days",
                }

        # 7. Diagnostic Warnings Grouped by Severity
        elif ("warning" in q_lower or "fault" in q_lower or "dtc" in q_lower or "diagnostic" in q_lower) and ("severity" in q_lower or "recent" in q_lower or "group" in q_lower or "list" in q_lower):
            intent = "DIAGNOSTIC_WARNINGS_GROUPED"
            entities = {"types": ["DIAGNOSTIC_WARNING", "CRITICAL", "WARNING"]}

        # 8. Vehicle Summary / Activity
        elif "summary" in q_lower or "status" in q_lower or "overview" in q_lower or "activity" in q_lower:
            intent = "VEHICLE_ACTIVITY_SUMMARY"
            entities = {}

        # 9. Direct Signal Lookup
        elif any(s in q_lower for s in ["speed", "velocity", "soc", "state of charge"]):
            intent = "DIRECT_SIGNAL_LOOKUP"
            sig = "vehicle_speed" if "speed" in q_lower or "velocity" in q_lower else "state_of_charge"
            entities = {"signal_name": sig}

        # Non-automotive / Unsupported questions
        else:
            intent = "UNSUPPORTED"
            entities = {}
            clarification = (
                "VehicleGPT supports natural language questions concerning vehicle telemetry, diagnostic warnings, "
                "ADAS disengagements, battery thermal status, and driving range trends. "
                "Try questions such as: 'Show all ADAS disengagement events from yesterday', "
                "'Why has my driving range reduced over the last two weeks?', "
                "or 'What happened before the battery overheating warning?'"
            )

        return ParsedQuery(
            raw_question=q_clean,
            intent=intent,
            time_window=time_window,
            entities=entities,
            is_supported=(intent != "UNSUPPORTED"),
            clarification_note=clarification,
        )

    def _extract_time_window(self, text: str, user_start: Optional[str], user_end: Optional[str]) -> dict[str, Optional[str]]:
        """Extract explicit or relative time ranges from query text."""
        if user_start:
            return {"start": user_start, "end": user_end or self.anchor_time.isoformat(), "label": "user specified"}

        # Relative keywords
        if "yesterday" in text:
            yesterday_date = (self.anchor_time - timedelta(days=1)).date()
            start_dt = datetime.combine(yesterday_date, datetime.min.time(), tzinfo=timezone.utc)
            end_dt = datetime.combine(yesterday_date, datetime.max.time(), tzinfo=timezone.utc)
            return {"start": start_dt.isoformat(), "end": end_dt.isoformat(), "label": "yesterday"}

        if "today" in text:
            today_date = self.anchor_time.date()
            start_dt = datetime.combine(today_date, datetime.min.time(), tzinfo=timezone.utc)
            return {"start": start_dt.isoformat(), "end": self.anchor_time.isoformat(), "label": "today"}

        if "two weeks" in text or "2 weeks" in text or "fortnight" in text:
            start_dt = self.anchor_time - timedelta(days=14)
            return {"start": start_dt.isoformat(), "end": self.anchor_time.isoformat(), "label": "last two weeks"}

        if "7 days" in text or "last week" in text or "past week" in text:
            start_dt = self.anchor_time - timedelta(days=7)
            return {"start": start_dt.isoformat(), "end": self.anchor_time.isoformat(), "label": "past 7 days"}

        if "month" in text or "30 days" in text:
            start_dt = self.anchor_time - timedelta(days=30)
            return {"start": start_dt.isoformat(), "end": self.anchor_time.isoformat(), "label": "last 30 days"}

        # Check for explicit ISO date strings like YYYY-MM-DD
        iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        if iso_match:
            date_str = iso_match.group(1)
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                s_dt = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
                e_dt = datetime.combine(d, datetime.max.time(), tzinfo=timezone.utc)
                return {"start": s_dt.isoformat(), "end": e_dt.isoformat(), "label": date_str}
            except Exception:
                pass

        return {"start": None, "end": None, "label": "unspecified"}
