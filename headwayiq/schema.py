"""Declarative schemas for HeadwayIQ Phase 1 datasets.

This module is the single source of truth for dataset shape, provenance values,
and the SQLite column mapping. Validation (validation.py), storage (db.py) and
the data dictionary all derive from the definitions here, so a rule is written
once and reused everywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Provenance classification. Extend this set rather than inventing new labels.
PROVENANCE = (
    "observed",            # measured from the real system
    "official_published",  # taken verbatim from an official published source
    "synthetic",           # invented for demonstration; NOT real-world evidence
    "estimated",           # derived/assumed from indirect evidence
    "manually_entered",    # hand-prepared scenario input
)

DIRECTIONS = ("northbound", "southbound", "eastbound", "westbound")
# day_type: GMRC publishes distinct weekday / Saturday / Sunday frequencies, so
# saturday and sunday are first-class values (not folded into "weekend").
DAY_TYPES = ("weekday", "saturday", "sunday", "weekend", "holiday")
EVENT_TYPES = ("sports", "festival", "exam", "holiday", "concert", "other")
WEATHER_CONDITIONS = ("clear", "clouds", "rain", "heavy_rain", "fog", "heat")


@dataclass(frozen=True)
class Field:
    name: str
    kind: str                      # string|int|float|date|time|enum
    required: bool = True          # must the column be present and non-empty
    nullable: bool = False         # may the value be blank (= unknown)
    allowed: tuple = ()            # permitted values when kind == "enum"
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class Schema:
    name: str
    pk: str                        # column whose values must be unique
    fields: list[Field]
    has_time_band: bool = False    # has time_band_start/time_band_end
    nonoverlap_keys: tuple = ()    # group columns within which bands must not overlap
    sql: str = ""                  # CREATE TABLE statement

    def field(self, name: str) -> Field | None:
        return next((f for f in self.fields if f.name == name), None)


def _prov(required: bool = True) -> Field:
    return Field("data_status", "enum", required=required, allowed=PROVENANCE)


_TIMETABLE = Schema(
    name="timetable",
    pk="service_id",
    has_time_band=True,
    nonoverlap_keys=("day_type", "line_id", "direction"),
    fields=[
        Field("service_id", "string"),
        Field("day_type", "enum", allowed=DAY_TYPES),
        Field("line_id", "string"),
        Field("direction", "enum", allowed=DIRECTIONS),
        Field("time_band_start", "time"),
        Field("time_band_end", "time"),
        Field("baseline_headway_minutes", "float", min=0.1, max=120),
        Field("source_reference", "string", nullable=True),
        _prov(),
        Field("notes", "string", required=False, nullable=True),
    ],
    sql="""
        CREATE TABLE IF NOT EXISTS timetable (
            service_id TEXT PRIMARY KEY,
            day_type TEXT NOT NULL,
            line_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            time_band_start TEXT NOT NULL,
            time_band_end TEXT NOT NULL,
            baseline_headway_minutes REAL NOT NULL CHECK (baseline_headway_minutes > 0),
            source_reference TEXT,
            data_status TEXT NOT NULL,
            notes TEXT,
            CHECK (time_band_start < time_band_end)
        )""",
)

_DEMAND = Schema(
    name="demand_profile",
    pk="profile_id",
    has_time_band=True,
    nonoverlap_keys=("day_type", "station_or_corridor_id", "direction"),
    fields=[
        Field("profile_id", "string"),
        Field("day_type", "enum", allowed=DAY_TYPES),
        Field("time_band_start", "time"),
        Field("time_band_end", "time"),
        Field("direction", "enum", allowed=DIRECTIONS),
        Field("estimated_passengers_per_hour", "int", min=0, max=200000),
        Field("station_or_corridor_id", "string", nullable=True),
        _prov(),
        Field("source_reference", "string", nullable=True),
        Field("assumptions", "string", required=False, nullable=True),
    ],
    sql="""
        CREATE TABLE IF NOT EXISTS demand_profile (
            profile_id TEXT PRIMARY KEY,
            day_type TEXT NOT NULL,
            time_band_start TEXT NOT NULL,
            time_band_end TEXT NOT NULL,
            direction TEXT NOT NULL,
            estimated_passengers_per_hour INTEGER NOT NULL
                CHECK (estimated_passengers_per_hour >= 0),
            station_or_corridor_id TEXT,
            data_status TEXT NOT NULL,
            source_reference TEXT,
            assumptions TEXT,
            CHECK (time_band_start < time_band_end)
        )""",
)

_EVENT = Schema(
    name="event",
    pk="event_id",
    fields=[
        Field("event_id", "string"),
        Field("event_name", "string"),
        Field("event_type", "enum", allowed=EVENT_TYPES),
        Field("event_date", "date"),
        Field("start_time", "time", nullable=True),
        Field("expected_end_time", "time", nullable=True),
        Field("venue_or_location", "string", nullable=True),
        Field("expected_attendance", "int", nullable=True, min=0, max=5000000),
        Field("affected_corridors_or_stations", "string", nullable=True),
        Field("source_reference", "string", nullable=True),
        _prov(),
        Field("notes", "string", required=False, nullable=True),
    ],
    sql="""
        CREATE TABLE IF NOT EXISTS event (
            event_id TEXT PRIMARY KEY,
            event_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            start_time TEXT,
            expected_end_time TEXT,
            venue_or_location TEXT,
            expected_attendance INTEGER CHECK (expected_attendance IS NULL OR expected_attendance >= 0),
            affected_corridors_or_stations TEXT,
            source_reference TEXT,
            data_status TEXT NOT NULL,
            notes TEXT
        )""",
)

_WEATHER = Schema(
    name="weather",
    pk="weather_id",
    has_time_band=True,
    fields=[
        Field("weather_id", "string"),
        Field("forecast_date", "date"),
        Field("time_band_start", "time"),
        Field("time_band_end", "time"),
        Field("location", "string"),
        Field("temperature_celsius", "float", nullable=True, min=-50, max=60),
        Field("precipitation_mm", "float", nullable=True, min=0, max=1000),
        Field("weather_condition", "enum", allowed=WEATHER_CONDITIONS),
        Field("source_reference", "string", nullable=True),
        _prov(),
        Field("notes", "string", required=False, nullable=True),
    ],
    sql="""
        CREATE TABLE IF NOT EXISTS weather (
            weather_id TEXT PRIMARY KEY,
            forecast_date TEXT NOT NULL,
            time_band_start TEXT NOT NULL,
            time_band_end TEXT NOT NULL,
            location TEXT NOT NULL,
            temperature_celsius REAL,
            precipitation_mm REAL CHECK (precipitation_mm IS NULL OR precipitation_mm >= 0),
            weather_condition TEXT NOT NULL,
            source_reference TEXT,
            data_status TEXT NOT NULL,
            notes TEXT,
            CHECK (time_band_start < time_band_end)
        )""",
)

# dataset key -> (Schema, fixture filename). Order matters for load/report.
SCHEMAS: dict[str, Schema] = {
    "timetable": _TIMETABLE,
    "demand_profile": _DEMAND,
    "event": _EVENT,
    "weather": _WEATHER,
}

FIXTURES: dict[str, list[str]] = {
    "timetable": ["timetable.csv"],
    "demand_profile": ["demand_weekday.csv", "demand_weekend.csv"],
    "event": ["events.csv"],
    "weather": ["weather.csv"],
}
