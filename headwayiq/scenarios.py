"""Seven reproducible demo scenarios for HeadwayIQ.

Each scenario resolves to a context dict consumed by engine.generate(). Scenarios
are deterministic (fixed inputs, no clock, no network) so a demo regenerates the
same recommendations every time. Event rows are pulled from the committed
fixtures; weather presets are explicit scenario inputs (manually_entered).

The engine selects active events/weather by corridor and time band, so a
scenario simply lists which signals are in play — it never edits the timetable.
"""
from __future__ import annotations

from . import db
from .engine import generate


def _event(event_id: str) -> dict:
    for r in db.load_fixture_rows("event"):
        if r["event_id"] == event_id:
            return dict(r)
    raise KeyError(event_id)


def _wx(wid: str, start: str, end: str, cond: str) -> dict:
    return {"weather_id": wid, "time_band_start": start, "time_band_end": end,
            "weather_condition": cond, "data_status": "manually_entered"}


# Weather presets (explicit scenario inputs, not a live forecast).
CLEAR = [_wx("WX-CLEAR", "05:00", "23:00", "clear")]
RAIN_PM = [_wx("WX-C", "05:00", "16:00", "clear"),
           _wx("WX-HR", "16:00", "20:00", "heavy_rain"),
           _wx("WX-R", "20:00", "23:00", "rain")]


# name -> context builder. Lazy builders so fixtures are read only when run.
_BUILDERS = {
    "normal_weekday": lambda: dict(
        title="Normal weekday",
        description="Typical weekday, clear weather, no events — baseline service.",
        date="2026-10-13", day_type="weekday", events=[], weather=CLEAR),
    "weekend_leisure": lambda: dict(
        title="Weekend (leisure pattern)",
        description="Saturday leisure demand, clear weather, no events.",
        date="2026-10-17", day_type="weekend", events=[], weather=CLEAR),
    "stadium_evening": lambda: dict(
        title="Stadium match — evening",
        description="Evening sports event on the NS corridor; clear weather.",
        date="2026-10-15", day_type="weekday", events=[_event("EV-1")], weather=CLEAR),
    "heavy_rain_pm": lambda: dict(
        title="Heavy rain — PM peak",
        description="Heavy rain over the afternoon/evening; no events.",
        date="2026-07-20", day_type="weekday", events=[], weather=RAIN_PM),
    "stadium_and_rain": lambda: dict(
        title="Stadium match + heavy rain",
        description="Evening sports event compounded by heavy afternoon rain.",
        date="2026-10-15", day_type="weekday", events=[_event("EV-1")], weather=RAIN_PM),
    "festival_holiday": lambda: dict(
        title="Public holiday with festival",
        description="Public holiday (reduced commuting) with an evening festival.",
        date="2026-11-08", day_type="holiday",
        events=[_event("EV-2"), _event("EV-3")], weather=CLEAR),
    "weather_unavailable": lambda: dict(
        title="Weather feed unavailable",
        description="Weekday with no weather data — recommendations flag the gap.",
        date="2026-10-13", day_type="weekday", events=[], weather=None),
}


def list_scenarios() -> list[dict]:
    out = []
    for name, build in _BUILDERS.items():
        c = build()
        out.append({"name": name, "title": c["title"], "description": c["description"]})
    return out


def context(name: str) -> dict:
    return dict(name=name, **_BUILDERS[name]())


def run(name: str) -> dict:
    """Resolve a scenario by name and return its full recommendation payload."""
    if name not in _BUILDERS:
        raise KeyError(f"unknown scenario {name!r}; choose from {list(_BUILDERS)}")
    return generate(context(name))
