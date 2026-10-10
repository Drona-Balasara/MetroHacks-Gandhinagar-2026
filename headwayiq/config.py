"""Tunable, deterministic parameters for the HeadwayIQ recommendation engine.

Every number that shapes a recommendation lives here so the logic is auditable
and adjustable without touching the engine. All demand multipliers are
ILLUSTRATIVE planning assumptions, not measured elasticities (see
docs/DATA_SOURCES.md). No value here is a claim about real GMRC ridership.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Canonical planning bands (HH:MM) the engine reasons over. These are the coarse
# demand bands from the synthetic profiles; the timetable supplies the reference
# headway covering each band's start time.
PLANNING_BANDS: tuple[tuple[str, str], ...] = (
    ("05:00", "07:00"),
    ("07:00", "10:00"),
    ("10:00", "16:00"),
    ("16:00", "20:00"),
    ("20:00", "23:00"),
)


@dataclass(frozen=True)
class Config:
    # Operating limits — a recommendation never leaves this range.
    min_headway: float = 3.0          # minutes; floor set by rolling-stock/turnaround
    max_headway: float = 20.0         # minutes; ceiling for an acceptable wait
    round_to: float = 0.5             # round recommended headway to nearest, minutes

    # Demand multipliers by event type, applied only to overlapping bands on the
    # affected corridor(s). >1 means "more people likely to ride than a normal day".
    event_factor: dict = field(default_factory=lambda: {
        "sports": 1.5,
        "concert": 1.4,
        "festival": 1.3,
        "exam": 1.2,
        "holiday": 1.0,   # holiday handled via day-type remap + holiday_factor, not here
        "other": 1.1,
    })

    # Weather multipliers (people shift onto the metro in bad weather; illustrative).
    weather_factor: dict = field(default_factory=lambda: {
        "clear": 1.0,
        "clouds": 1.0,
        "fog": 1.05,
        "heat": 1.05,
        "rain": 1.15,
        "heavy_rain": 1.25,
    })

    # A public holiday damps commuting overall (applied to every band that day).
    holiday_factor: float = 0.8

    # The combined multiplier is clamped so no single scenario explodes demand.
    cumulative_min: float = 0.5
    cumulative_max: float = 2.5

    # Deadband around 1.0: within it, demand is "normal" and headway is unchanged.
    deadband_low: float = 0.85
    deadband_high: float = 1.15
    # Upper label threshold: factor above this is "high", else "elevated".
    high_level: float = 1.4


DEFAULT = Config()
