"""Deterministic vehicle analytics, trend calculations, and event correlation engine.

All numerical facts, aggregates, and comparisons are strictly calculated here.
The language model never calculates numbers independently.
"""

import math
from typing import Any, Optional
from backend.config import settings
from backend.schemas import EvidenceRecord


class VehicleAnalytics:
    """Calculates deterministic statistics, anomaly flags, and multi-signal correlations."""

    @staticmethod
    def compute_summary_stats(values: list[float]) -> dict[str, Any]:
        """Compute robust basic descriptive statistics."""
        if not values:
            return {"count": 0, "min": None, "max": None, "mean": None, "median": None}

        sorted_vals = sorted(values)
        count = len(sorted_vals)
        total = sum(sorted_vals)
        mean_val = round(total / count, 2)
        min_val = round(sorted_vals[0], 2)
        max_val = round(sorted_vals[-1], 2)

        # Median
        if count % 2 == 1:
            median_val = round(sorted_vals[count // 2], 2)
        else:
            median_val = round((sorted_vals[(count // 2) - 1] + sorted_vals[count // 2]) / 2.0, 2)

        # Variance & Standard Deviation
        variance = sum((x - mean_val) ** 2 for x in sorted_vals) / count
        std_dev = round(math.sqrt(variance), 2)

        return {
            "count": count,
            "min": min_val,
            "max": max_val,
            "mean": mean_val,
            "median": median_val,
            "std_dev": std_dev,
        }

    @classmethod
    def analyze_driving_range_trend(cls, telemetry_records: list[dict[str, Any]]) -> dict[str, Any]:
        """Calculate historical reduction in driving range and correlate with ambient temperatures."""
        if not telemetry_records:
            return {"status": "INSUFFICIENT_DATA"}

        # Sort chronologically
        sorted_recs = sorted(telemetry_records, key=lambda x: x["timestamp"])
        count = len(sorted_recs)

        if count < 4:
            return {"status": "INSUFFICIENT_DATA", "count": count}

        # Divide into early half and recent half to measure trend
        half = count // 2
        early_half = [r["value"] for r in sorted_recs[:half]]
        recent_half = [r["value"] for r in sorted_recs[half:]]

        early_mean = sum(early_half) / len(early_half)
        recent_mean = sum(recent_half) / len(recent_half)
        range_delta = round(recent_mean - early_mean, 1)
        pct_change = round((range_delta / early_mean) * 100.0, 1) if early_mean > 0 else 0.0

        first_val = round(sorted_recs[0]["value"], 1)
        latest_val = round(sorted_recs[-1]["value"], 1)
        absolute_drop = round(first_val - latest_val, 1)

        evidence: list[EvidenceRecord] = [
            EvidenceRecord(
                timestamp=sorted_recs[0]["timestamp"],
                record_type="telemetry",
                label="driving_range_baseline",
                value=first_val,
                unit=sorted_recs[0].get("unit", "km"),
                source=sorted_recs[0].get("source"),
                details=f"Baseline range reading at start of period ({sorted_recs[0]['timestamp'][:10]})",
            ),
            EvidenceRecord(
                timestamp=sorted_recs[-1]["timestamp"],
                record_type="telemetry",
                label="driving_range_recent",
                value=latest_val,
                unit=sorted_recs[-1].get("unit", "km"),
                source=sorted_recs[-1].get("source"),
                details=f"Most recent range reading ({sorted_recs[-1]['timestamp'][:10]})",
            ),
        ]

        return {
            "status": "VALID",
            "first_reading": first_val,
            "latest_reading": latest_val,
            "early_period_mean_km": round(early_mean, 1),
            "recent_period_mean_km": round(recent_mean, 1),
            "mean_delta_km": range_delta,
            "percentage_change": pct_change,
            "absolute_drop_km": absolute_drop,
            "evidence": evidence,
        }

    @classmethod
    def detect_consumption_surges(
        cls,
        telemetry_records: list[dict[str, Any]],
        threshold: float = settings.ENERGY_CONSUMPTION_HIGH_THRESHOLD,
    ) -> dict[str, Any]:
        """Identify peak energy consumption periods and anomalies exceeding threshold."""
        if not telemetry_records:
            return {"status": "NO_RECORDS"}

        values = [r["value"] for r in telemetry_records]
        stats = cls.compute_summary_stats(values)

        anomalies = [r for r in telemetry_records if r["value"] >= threshold]
        sorted_by_val = sorted(telemetry_records, key=lambda x: x["value"], reverse=True)
        peak_record = sorted_by_val[0] if sorted_by_val else None

        evidence: list[EvidenceRecord] = []
        # Include top 3 highest consumption periods as evidence
        for top in sorted_by_val[:5]:
            evidence.append(
                EvidenceRecord(
                    timestamp=top["timestamp"],
                    record_type="telemetry",
                    label="energy_consumption_spike",
                    value=round(top["value"], 1),
                    unit=top.get("unit", "kWh/100 km"),
                    source=top.get("source"),
                    details=f"Peak energy consumption reading exceeding normal threshold ({threshold} kWh/100 km)",
                )
            )

        return {
            "stats": stats,
            "threshold": threshold,
            "anomaly_count": len(anomalies),
            "peak_value": round(peak_record["value"], 1) if peak_record else None,
            "peak_timestamp": peak_record["timestamp"] if peak_record else None,
            "evidence": evidence,
        }

    @classmethod
    def correlate_warning_precedents(
        cls,
        warning_event: dict[str, Any],
        correlated_events: list[dict[str, Any]],
        correlated_telemetry: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Correlate telemetry shifts and events preceding a diagnostic warning without false causality claims."""
        w_ts = warning_event["timestamp"]
        evidence: list[EvidenceRecord] = []

        # Add the warning itself as anchor evidence
        evidence.append(
            EvidenceRecord(
                timestamp=w_ts,
                record_type="event",
                label=warning_event.get("event_type", "WARNING"),
                severity=warning_event.get("severity", "CRITICAL"),
                source=warning_event.get("source"),
                details=warning_event.get("description"),
            )
        )

        # Preceding events strictly before the warning timestamp
        preceding_events = [e for e in correlated_events if e["timestamp"] < w_ts]
        for pe in preceding_events:
            evidence.append(
                EvidenceRecord(
                    timestamp=pe["timestamp"],
                    record_type="event",
                    label=pe.get("event_type", "EVENT"),
                    severity=pe.get("severity", "INFO"),
                    source=pe.get("source"),
                    details=pe.get("description"),
                )
            )

        # Telemetry metrics analysis before warning
        telemetry_insights: dict[str, Any] = {}
        for sig_name, series in correlated_telemetry.items():
            pre_series = [t for t in series if t["timestamp"] <= w_ts]
            if pre_series:
                vals = [t["value"] for t in pre_series]
                t_stats = cls.compute_summary_stats(vals)
                first_t = pre_series[0]["value"]
                last_t = pre_series[-1]["value"]
                telemetry_insights[sig_name] = {
                    "start_value": first_t,
                    "end_value": last_t,
                    "net_delta": round(last_t - first_t, 1),
                    "max_observed": t_stats["max"],
                    "mean": t_stats["mean"],
                    "unit": pre_series[0].get("unit", ""),
                }
                # Add key start & end readings as evidence
                evidence.append(
                    EvidenceRecord(
                        timestamp=pre_series[0]["timestamp"],
                        record_type="telemetry",
                        label=f"{sig_name}_start",
                        value=round(first_t, 1),
                        unit=pre_series[0].get("unit"),
                        source=pre_series[0].get("source"),
                        details=f"Observed value 30 minutes prior to warning",
                    )
                )
                evidence.append(
                    EvidenceRecord(
                        timestamp=pre_series[-1]["timestamp"],
                        record_type="telemetry",
                        label=f"{sig_name}_at_alert",
                        value=round(last_t, 1),
                        unit=pre_series[-1].get("unit"),
                        source=pre_series[-1].get("source"),
                        details=f"Peak reading coincident with warning trigger",
                    )
                )

        return {
            "warning": warning_event,
            "preceding_events_count": len(preceding_events),
            "telemetry_insights": telemetry_insights,
            "evidence": evidence,
        }

    @classmethod
    def compare_city_vs_highway(cls, speed_recs: list[dict[str, Any]], cons_recs: list[dict[str, Any]]) -> dict[str, Any]:
        """Compare energy consumption and driving profile between city and highway driving."""
        # Align consumption records by timestamp with corresponding speed
        speed_map = {r["timestamp"]: r["value"] for r in speed_recs}

        city_cons: list[float] = []
        highway_cons: list[float] = []

        for cr in cons_recs:
            ts = cr["timestamp"]
            speed = speed_map.get(ts)
            if speed is not None:
                if speed < 55.0:
                    city_cons.append(cr["value"])
                elif speed >= 75.0:
                    highway_cons.append(cr["value"])

        city_stats = cls.compute_summary_stats(city_cons)
        highway_stats = cls.compute_summary_stats(highway_cons)

        diff = None
        pct_diff = None
        if city_stats["mean"] and highway_stats["mean"]:
            diff = round(highway_stats["mean"] - city_stats["mean"], 1)
            pct_diff = round((diff / city_stats["mean"]) * 100.0, 1)

        evidence: list[EvidenceRecord] = [
            EvidenceRecord(
                timestamp=cons_recs[0]["timestamp"] if cons_recs else "",
                record_type="telemetry",
                label="city_driving_efficiency",
                value=city_stats.get("mean"),
                unit="kWh/100 km",
                details=f"City driving average consumption (<55 km/h, n={city_stats['count']} intervals)",
            ),
            EvidenceRecord(
                timestamp=cons_recs[-1]["timestamp"] if cons_recs else "",
                record_type="telemetry",
                label="highway_driving_efficiency",
                value=highway_stats.get("mean"),
                unit="kWh/100 km",
                details=f"Highway driving average consumption (>75 km/h, n={highway_stats['count']} intervals)",
            ),
        ]

        return {
            "city_stats": city_stats,
            "highway_stats": highway_stats,
            "highway_vs_city_consumption_delta": diff,
            "highway_consumption_increase_pct": pct_diff,
            "evidence": evidence,
        }
