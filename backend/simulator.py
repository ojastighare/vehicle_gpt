"""Deterministic vehicle data simulator for VehicleGPT.

Generates realistic telemetry streams, diagnostic DTC logs, and vehicle events
over several weeks of temporal history with predictable fault scenarios.
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any


class VehicleDataSimulator:
    """Simulates realistic electric vehicle telemetry and events."""

    def __init__(self, seed: int = 42, base_date: datetime | None = None):
        self.seed = seed
        self.random = random.Random(seed)
        # 2026-10-22 as current reference anchor matching execution metadata
        self.anchor_time = base_date or datetime(2026, 10, 22, 14, 0, 0, tzinfo=timezone.utc)

    def generate_dataset(self, days: int = 21) -> dict[str, list[dict[str, Any]]]:
        """Generate historical vehicle records spanning specified days."""
        self.random.seed(self.seed)
        telemetry_records: list[dict[str, Any]] = []
        event_records: list[dict[str, Any]] = []
        diagnostic_records: list[dict[str, Any]] = []

        start_time = self.anchor_time - timedelta(days=days)
        current_time = start_time

        # Cumulative odometer state
        odometer_km = 14200.0
        current_soc = 88.0

        day_index = 0
        while current_time <= self.anchor_time:
            day_offset = (current_time - start_time).total_seconds() / 86400.0
            date_str = current_time.strftime("%Y-%m-%d")

            # Ambient temperature drops over the 3-week span: 28°C down to 5°C
            ambient_temp = 28.0 - (day_offset * 1.1) + self.random.uniform(-1.5, 1.5)

            # Heater power demand increases as ambient temperature drops
            heater_power_kw = max(0.2, (22.0 - ambient_temp) * 0.18) if ambient_temp < 20 else 0.2

            # Baseline driving range decreases with colder battery & heating draw
            # Range drops from ~420km down to ~340km
            temp_range_penalty = max(0.0, (25.0 - ambient_temp) * 3.8)
            full_charge_range = 420.0 - temp_range_penalty

            # Morning Commute: 07:30 - 08:15 UTC (City driving)
            commute_morning = current_time.replace(hour=7, minute=30, second=0)
            if commute_morning <= self.anchor_time and commute_morning >= current_time:
                t_recs, e_recs = self._simulate_trip(
                    start_t=commute_morning,
                    duration_mins=45,
                    trip_type="CITY",
                    ambient_temp=ambient_temp,
                    heater_kw=heater_power_kw,
                    full_range=full_charge_range,
                    initial_soc=current_soc,
                )
                telemetry_records.extend(t_recs)
                event_records.extend(e_recs)
                if t_recs:
                    current_soc = max(15.0, t_recs[-1]["soc_end"])

            # Evening Commute: 17:15 - 18:05 UTC (Highway / Mixed)
            commute_evening = current_time.replace(hour=17, minute=15, second=0)
            if commute_evening <= self.anchor_time and commute_evening >= current_time:
                t_recs, e_recs = self._simulate_trip(
                    start_t=commute_evening,
                    duration_mins=50,
                    trip_type="HIGHWAY",
                    ambient_temp=ambient_temp - 2.0,
                    heater_kw=heater_power_kw + 0.3,
                    full_range=full_charge_range,
                    initial_soc=current_soc,
                )
                telemetry_records.extend(t_recs)
                event_records.extend(e_recs)
                if t_recs:
                    current_soc = max(15.0, t_recs[-1]["soc_end"])

            # Night Charging: 23:00 UTC (Recharge to 90%)
            charging_time = current_time.replace(hour=23, minute=0, second=0)
            if charging_time <= self.anchor_time and charging_time >= current_time:
                event_records.append({
                    "timestamp": charging_time.isoformat(),
                    "event_type": "CHARGING_SESSION",
                    "severity": "INFO",
                    "description": f"Home AC Level 2 charging initiated. SoC replenished from {current_soc:.1f}% to 90.0%.",
                    "source": "BMS_HAL",
                    "metadata": '{"charge_type": "AC_LEVEL_2", "target_soc": 90.0}',
                })
                current_soc = 90.0

            # Advance by 1 day
            current_time += timedelta(days=1)
            day_index += 1

        # Inject Fault Scenarios
        # Scenario 1: Oct 18, 2026 - High Speed Highway Climb -> Battery Overheating Warning
        scenario_1_time = datetime(2026, 10, 18, 14, 10, 0, tzinfo=timezone.utc)
        s1_telemetry, s1_events, s1_diags = self._generate_battery_overheat_scenario(scenario_1_time)
        telemetry_records.extend(s1_telemetry)
        event_records.extend(s1_events)
        diagnostic_records.extend(s1_diags)

        # Scenario 2: Yesterday (Oct 21, 2026) - Specific ADAS Disengagements
        yesterday_date = (self.anchor_time - timedelta(days=1)).date()
        s2_events = self._generate_yesterday_adas_events(yesterday_date)
        event_records.extend(s2_events)

        # Sort all datasets by timestamp
        telemetry_records.sort(key=lambda x: x["timestamp"])
        event_records.sort(key=lambda x: x["timestamp"])
        diagnostic_records.sort(key=lambda x: x["timestamp"])

        return {
            "telemetry": telemetry_records,
            "events": event_records,
            "diagnostics": diagnostic_records,
        }

    def _simulate_trip(
        self,
        start_t: datetime,
        duration_mins: int,
        trip_type: str,
        ambient_temp: float,
        heater_kw: float,
        full_range: float,
        initial_soc: float,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Simulate realistic trip telemetry and trip lifecycle events."""
        telemetry: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        events.append({
            "timestamp": start_t.isoformat(),
            "event_type": "TRIP_START",
            "severity": "INFO",
            "description": f"{trip_type.title()} driving commute started. Initial SoC: {initial_soc:.1f}%.",
            "source": "VCU_TRIP_MONITOR",
            "metadata": f'{{"trip_type": "{trip_type}", "soc_start": {initial_soc:.1f}}}',
        })

        t_cursor = start_t
        soc = initial_soc
        batt_temp = max(18.0, ambient_temp + 3.0)

        # Step every 5 minutes during trip to maintain compact size and high speed
        step_mins = 5
        steps = duration_mins // step_mins

        for i in range(steps):
            t_cursor += timedelta(minutes=step_mins)
            ts_str = t_cursor.isoformat()

            if trip_type == "CITY":
                speed = self.random.uniform(15.0, 48.0)
                # City driving: low aerodynamic drag, regen braking helps, consumption ~ 14.5 - 16.5 kWh/100km
                base_consumption = 14.5 + self.random.uniform(-1.0, 1.8)
                batt_temp = min(36.0, batt_temp + self.random.uniform(0.1, 0.4))
            else:  # HIGHWAY
                speed = self.random.uniform(85.0, 115.0)
                # Highway driving: continuous aerodynamic drag, consumption ~ 20.5 - 23.5 kWh/100km
                base_consumption = 21.0 + self.random.uniform(-1.2, 2.5)
                batt_temp = min(41.0, batt_temp + self.random.uniform(0.4, 0.9))

            # Heating penalty increases consumption
            consumption = base_consumption + (heater_kw * 1.8)

            # Energy drained decreases SoC
            soc_delta = (consumption * (speed * (step_mins / 60.0)) / 75.0) * 1.15
            soc = max(5.0, soc - soc_delta)
            driving_range = (soc / 100.0) * full_range

            telemetry.append({
                "timestamp": ts_str,
                "signal_name": "vehicle_speed",
                "value": round(speed, 1),
                "unit": "km/h",
                "source": "CAN_BUS",
                "soc_end": soc,
            })
            telemetry.append({
                "timestamp": ts_str,
                "signal_name": "battery_temperature",
                "value": round(batt_temp, 1),
                "unit": "°C",
                "source": "BMS_HAL",
                "soc_end": soc,
            })
            telemetry.append({
                "timestamp": ts_str,
                "signal_name": "state_of_charge",
                "value": round(soc, 1),
                "unit": "%",
                "source": "BMS_HAL",
                "soc_end": soc,
            })
            telemetry.append({
                "timestamp": ts_str,
                "signal_name": "energy_consumption",
                "value": round(consumption, 1),
                "unit": "kWh/100 km",
                "source": "VCU_POWERTRAIN",
                "soc_end": soc,
            })
            telemetry.append({
                "timestamp": ts_str,
                "signal_name": "driving_range",
                "value": round(driving_range, 1),
                "unit": "km",
                "source": "VCU_RANGE_EST",
                "soc_end": soc,
            })

            # Occasional ADAS disengagement in traffic or merge (10% chance)
            if self.random.random() < 0.08:
                events.append({
                    "timestamp": ts_str,
                    "event_type": "ADAS_DISENGAGEMENT",
                    "severity": "INFO",
                    "description": "Lane Centering disengaged: driver nudged steering wheel for route merge.",
                    "source": "ADAS_ECU",
                    "metadata": '{"reason": "DRIVER_OVERRIDE", "system": "LANE_CENTRING"}',
                })

        events.append({
            "timestamp": t_cursor.isoformat(),
            "event_type": "TRIP_END",
            "severity": "INFO",
            "description": f"{trip_type.title()} trip concluded. Final SoC: {soc:.1f}%.",
            "source": "VCU_TRIP_MONITOR",
            "metadata": f'{{"trip_type": "{trip_type}", "soc_end": {soc:.1f}}}',
        })

        return telemetry, events

    def _generate_battery_overheat_scenario(
        self, start_t: datetime
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Simulate high-speed steep incline triggering battery overheating warning."""
        telemetry: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []

        curr = start_t
        batt_temp = 34.0
        soc = 62.0

        # High ambient temperature on that day
        # 14:10 to 14:25 - Normal high speed climb
        for m in range(0, 15, 3):
            curr = start_t + timedelta(minutes=m)
            ts = curr.isoformat()
            batt_temp += 1.6
            consumption = 24.5 + (m * 0.5)

            telemetry.append({
                "timestamp": ts,
                "signal_name": "vehicle_speed",
                "value": 112.0 + (m * 0.5),
                "unit": "km/h",
                "source": "CAN_BUS",
            })
            telemetry.append({
                "timestamp": ts,
                "signal_name": "battery_temperature",
                "value": round(batt_temp, 1),
                "unit": "°C",
                "source": "BMS_HAL",
            })
            telemetry.append({
                "timestamp": ts,
                "signal_name": "energy_consumption",
                "value": round(consumption, 1),
                "unit": "kWh/100 km",
                "source": "VCU_POWERTRAIN",
            })

        # 14:26 to 14:30 - Extreme steep uphill acceleration: Consumption spikes to 34.8 kWh/100 km
        for m in range(16, 21):
            curr = start_t + timedelta(minutes=m)
            ts = curr.isoformat()
            batt_temp += 1.4
            speed = 124.0
            consumption = 31.0 + (m - 16) * 1.1  # Peak ~ 35.4 kWh/100 km

            telemetry.append({
                "timestamp": ts,
                "signal_name": "vehicle_speed",
                "value": round(speed, 1),
                "unit": "km/h",
                "source": "CAN_BUS",
            })
            telemetry.append({
                "timestamp": ts,
                "signal_name": "battery_temperature",
                "value": round(batt_temp, 1),
                "unit": "°C",
                "source": "BMS_HAL",
            })
            telemetry.append({
                "timestamp": ts,
                "signal_name": "energy_consumption",
                "value": round(consumption, 1),
                "unit": "kWh/100 km",
                "source": "VCU_POWERTRAIN",
            })

        # At 14:31:00 UTC, Battery Temp crosses 47.1°C -> Trigger DTC Warning!
        warning_time = start_t + timedelta(minutes=21)
        warning_ts = warning_time.isoformat()

        # Telemetry right at alert
        telemetry.append({
            "timestamp": warning_ts,
            "signal_name": "battery_temperature",
            "value": 47.3,
            "unit": "°C",
            "source": "BMS_HAL",
        })
        telemetry.append({
            "timestamp": warning_ts,
            "signal_name": "energy_consumption",
            "value": 35.2,
            "unit": "kWh/100 km",
            "source": "VCU_POWERTRAIN",
        })

        events.append({
            "timestamp": warning_ts,
            "event_type": "DIAGNOSTIC_WARNING",
            "severity": "CRITICAL",
            "description": "BMS Alert: Battery pack thermal limit exceeded (47.3°C > 45.0°C threshold).",
            "source": "BMS_DIAGNOSTICS",
            "metadata": '{"dtc": "DTC_P0A80", "battery_temp": 47.3, "threshold": 45.0}',
        })

        diagnostics.append({
            "timestamp": warning_ts,
            "dtc_code": "DTC_BMS_TEMP_HIGH",
            "ecu": "BMS",
            "status": "CONFIRMED",
            "description": "High voltage battery module overtemperature condition detected.",
        })

        # Cool down & thermal derating applied shortly after
        derate_time = warning_time + timedelta(seconds=45)
        events.append({
            "timestamp": derate_time.isoformat(),
            "event_type": "POWERTRAIN_DERATING",
            "severity": "WARNING",
            "description": "VCU active thermal management: Motor power output curtailed to 60kW to protect battery cells.",
            "source": "VCU_THERMAL",
            "metadata": '{"derate_pct": 40.0}',
        })

        return telemetry, events, diagnostics

    def _generate_yesterday_adas_events(self, target_date: Any) -> list[dict[str, Any]]:
        """Generate verified ADAS disengagement events for yesterday."""
        events: list[dict[str, Any]] = []

        records = [
            (
                "08:14:22",
                "WARNING",
                "ADAS disengaged: Driver hands-off steering wheel exceeded 15s limit on Highway 101.",
                '{"reason": "HANDS_OFF_TIMEOUT", "speed_kmh": 82.5, "sensor": "CAPACITIVE_WHEEL"}',
            ),
            (
                "12:45:10",
                "INFO",
                "ADAS disengaged: Lane detection lost due to asphalt resurfacing and unpainted road segment.",
                '{"reason": "LANE_LINE_FADED", "speed_kmh": 46.0, "sensor": "FRONT_CAMERA"}',
            ),
            (
                "17:35:48",
                "INFO",
                "ADAS disengaged: Direct blinding sun glare detected by forward optical ADAS module.",
                '{"reason": "CAMERA_SUN_GLARE", "speed_kmh": 74.0, "sensor": "FRONT_CAMERA"}',
            ),
            (
                "18:10:05",
                "WARNING",
                "ADAS disengaged: Heavy rainfall caused front millimeter-wave radar sensor attenuation.",
                '{"reason": "RADAR_WEATHER_ATTENUATION", "speed_kmh": 58.0, "sensor": "RADAR_FRONT"}',
            ),
        ]

        for time_str, severity, desc, meta in records:
            dt = datetime.combine(
                target_date,
                datetime.strptime(time_str, "%H:%M:%S").time(),
                tzinfo=timezone.utc,
            )
            events.append({
                "timestamp": dt.isoformat(),
                "event_type": "ADAS_DISENGAGEMENT",
                "severity": severity,
                "description": desc,
                "source": "ADAS_ECU",
                "metadata": meta,
            })

        return events
