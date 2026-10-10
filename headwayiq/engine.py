"""Deterministic event/weather analysis, demand estimation and headway
recommendation for HeadwayIQ.

No LLM, no network, no randomness: identical inputs always produce identical
output. The pipeline is a chain of small, independently testable functions:

    analyse_band    -> which event/weather signals touch a corridor+band
    estimate (factor) -> baseline demand x clamped multiplier -> relative level
    recommend_band  -> reference headway vs recommended headway + action
    explain         -> plain-language, template-based rationale

Reference headways come from the OFFICIAL GMRC timetable; the demand baseline is
SYNTHETIC; the multipliers are ILLUSTRATIVE planning assumptions. None of this
is a claim about measured ridership (see docs/DATA_SOURCES.md).
"""
from __future__ import annotations

from collections import Counter
from datetime import date

from . import db
from .config import DEFAULT, PLANNING_BANDS, Config


# ---- time + day-type helpers ---------------------------------------------

def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")[:2]
    return int(h) * 60 + int(m)


def _overlap(a0: str, a1: str, b0: str, b1: str) -> bool:
    return _mins(a0) < _mins(b1) and _mins(b0) < _mins(a1)


def resolve_day_type(iso: str) -> str:
    """Calendar day-type from an ISO date (holidays are declared, not inferred)."""
    wd = date.fromisoformat(iso).weekday()
    return "saturday" if wd == 5 else "sunday" if wd == 6 else "weekday"


def _tt_day(dt: str) -> str:  # timetable publishes weekday/saturday/sunday only
    return {"weekday": "weekday", "saturday": "saturday", "sunday": "sunday",
            "weekend": "saturday", "holiday": "sunday"}[dt]


def _dm_day(dt: str) -> str:  # demand profiles exist for weekday/weekend only
    return "weekday" if dt == "weekday" else "weekend"


# ---- lookups --------------------------------------------------------------

def reference_bands(timetable: list[dict], line: str, direction: str, tt_day: str):
    """Sorted (start, end, headway) tuples for one line/direction/day pattern."""
    out = [(r["time_band_start"], r["time_band_end"], float(r["baseline_headway_minutes"]))
           for r in timetable
           if r["line_id"] == line and r["direction"] == direction
           and r["day_type"] == tt_day]
    return sorted(out, key=lambda b: _mins(b[0]))


def _ref_headway(ref_bands, band_start: str):
    for s, e, h in ref_bands:
        if _mins(s) <= _mins(band_start) < _mins(e):
            return h
    return None  # no scheduled service covering this band's start


def _baseline(demand, corridor, direction, dm_day, band):
    for r in demand:
        if (r["station_or_corridor_id"] == corridor and r["direction"] == direction
                and r["day_type"] == dm_day
                and r["time_band_start"] == band[0] and r["time_band_end"] == band[1]):
            return int(r["estimated_passengers_per_hour"])
    return None


# ---- analysis: event + weather signals for one corridor+band -------------

def _corridors_of(ev: dict) -> list[str]:
    aff = (ev.get("affected_corridors_or_stations") or "").upper()
    return [c.strip() for c in aff.replace(";", ",").split(",") if c.strip()]


def analyse_band(corridor: str, band, events: list[dict], weather, holiday: bool,
                 cfg: Config = DEFAULT):
    """Return (factor, signals, warnings) for one corridor + planning band.

    Each event contributes at most once; weather contributes the single most
    impactful overlapping condition. Missing/uncovered weather is reported, not
    silently assumed clear.
    """
    factor = 1.0
    signals: list[dict] = []

    for ev in events:
        if ev.get("event_type") == "holiday":
            continue  # a holiday remaps the day pattern (holiday flag), not a band factor
        corridors = _corridors_of(ev)
        if corridors and corridor not in corridors:
            continue
        start, end = ev.get("start_time"), ev.get("expected_end_time")
        if start:  # timed event: must overlap the band (untimed = affects whole day)
            if not _overlap(band[0], band[1], start, end or "23:59"):
                continue
        f = cfg.event_factor.get(ev.get("event_type"), cfg.event_factor["other"])
        factor *= f
        scope = "network-wide" if not corridors else f"on {corridor}"
        signals.append({"kind": "event", "ref": ev.get("event_id"),
                        "label": ev.get("event_name"), "factor": f,
                        "detail": f"{ev.get('event_type')} event {scope}"})

    warnings: list[str] = []
    if weather is None:
        warnings.append("no weather data supplied for this scenario")
    else:
        best = None
        for wx in weather:
            if _overlap(band[0], band[1], wx["time_band_start"], wx["time_band_end"]):
                cond = wx.get("weather_condition")
                f = cfg.weather_factor.get(cond, 1.0)
                if best is None or f > best[0]:
                    best = (f, cond, wx.get("weather_id"))
        if best is None:
            warnings.append("no weather band covers this time")
        elif best[0] != 1.0:
            factor *= best[0]
            signals.append({"kind": "weather", "ref": best[2], "label": best[1],
                            "factor": best[0], "detail": f"{best[1]} conditions"})

    if holiday:
        factor *= cfg.holiday_factor
        signals.append({"kind": "holiday", "ref": None, "label": "public holiday",
                        "factor": cfg.holiday_factor, "detail": "public-holiday travel pattern"})

    factor = max(cfg.cumulative_min, min(cfg.cumulative_max, factor))
    return factor, signals, warnings


def _level(factor: float, cfg: Config) -> str:
    if factor < cfg.deadband_low:
        return "below_normal"
    if factor <= cfg.deadband_high:
        return "normal"
    return "elevated" if factor <= cfg.high_level else "high"


# ---- recommendation + explanation ----------------------------------------

def recommend_band(ref, factor: float, cfg: Config = DEFAULT):
    """(recommended_headway, action) for a reference headway and demand factor.

    More demand -> shorter headway. Result is clamped to operating limits and
    rounded; within the deadband the reference headway is kept unchanged.
    """
    if ref is None:
        return None, "no_service"
    if cfg.deadband_low <= factor <= cfg.deadband_high:
        return ref, "maintain"
    raw = ref / factor
    rec = max(cfg.min_headway, min(cfg.max_headway, raw))
    rec = round(rec / cfg.round_to) * cfg.round_to
    if rec < ref:
        return rec, "increase_frequency"
    if rec > ref:
        return rec, "reduce_frequency"
    return ref, "maintain"  # clamp/rounding erased the change


def _fmt(mins) -> str:
    if mins is None:
        return "—"
    return f"{mins:g} min"


def explain(band, direction, ref, rec, action, level, signals, warnings) -> str:
    when = f"{band[0]}-{band[1]} {direction}"
    if action == "no_service":
        return f"{when}: no scheduled service in this band - no change."
    lvl = level.replace("_", " ")
    if action == "maintain":
        base = f"{when}: demand looks {lvl}; keep the {_fmt(ref)} headway."
    else:
        verb = ("increase service (shorter headway)" if action == "increase_frequency"
                else "reduce service (longer headway)")
        pct = (rec - ref) / ref * 100
        base = (f"{when}: estimated demand is {lvl}, so {verb} - "
                f"from {_fmt(ref)} to {_fmt(rec)} ({pct:+.0f}%).")
    if signals:
        base += " Drivers: " + "; ".join(f"{s['detail']} (x{s['factor']:g})" for s in signals) + "."
    if warnings:
        base += " Caveat: " + "; ".join(warnings) + "."
    base += (" Baseline demand is synthetic/illustrative; validate against live"
             " counts before operational use.")
    return base


# ---- top-level: run the whole pipeline for a resolved context -------------

def generate(context: dict, cfg: Config = DEFAULT, timetable=None, demand=None) -> dict:
    """Full recommendation payload for a resolved scenario context.

    context: {name?, title?, description?, date, day_type, events:[...], weather:[...]|None}
    weather=None means "no forecast available" (reported as a data-quality caveat).
    """
    timetable = db.load_fixture_rows("timetable") if timetable is None else timetable
    demand = db.load_fixture_rows("demand_profile") if demand is None else demand
    dt = context["day_type"]
    holiday = dt == "holiday"
    tt_day, dm_day = _tt_day(dt), _dm_day(dt)
    events = context.get("events") or []
    weather = context.get("weather")

    corridors = sorted({r["station_or_corridor_id"] for r in demand}
                       & {r["line_id"] for r in timetable})
    bands_out: list[dict] = []
    for line in corridors:
        for direction in sorted({r["direction"] for r in timetable if r["line_id"] == line}):
            ref_bands = reference_bands(timetable, line, direction, tt_day)
            if not ref_bands:
                continue
            for band in PLANNING_BANDS:
                factor, signals, warnings = analyse_band(line, band, events, weather, holiday, cfg)
                ref = _ref_headway(ref_bands, band[0])
                rec, action = recommend_band(ref, factor, cfg)
                level = _level(factor, cfg)
                baseline = _baseline(demand, line, direction, dm_day, band)
                est = round(baseline * factor) if baseline is not None else None
                bands_out.append({
                    "line": line, "direction": direction,
                    "band_start": band[0], "band_end": band[1], "day_type": dt,
                    "reference_headway_min": ref,
                    "recommended_headway_min": rec,
                    "action": action,
                    "change_min": round(rec - ref, 2) if (rec is not None and ref is not None) else None,
                    "change_pct": round((rec - ref) / ref * 100, 1) if (rec is not None and ref) else None,
                    "demand_factor": round(factor, 3),
                    "demand_level": level,
                    "baseline_pph": baseline,
                    "estimated_pph": est,
                    "signals": signals,
                    "warnings": warnings,
                    "explanation": explain(band, direction, ref, rec, action, level, signals, warnings),
                })

    counts = Counter(b["action"] for b in bands_out)
    return {
        "scenario": context.get("name"),
        "title": context.get("title"),
        "description": context.get("description"),
        "date": context.get("date"),
        "day_type": dt,
        "corridors": corridors,
        "provenance": {
            "timetable": "official_published — GMRC, effective 2026-05-18",
            "demand": "synthetic — illustrative shape only, not measured ridership",
            "events_weather": "manually_entered scenario inputs",
            "adjustments": "illustrative planning multipliers (headwayiq/config.py), not measured elasticities",
        },
        "summary": {
            "bands": len(bands_out),
            "increase_frequency": counts.get("increase_frequency", 0),
            "reduce_frequency": counts.get("reduce_frequency", 0),
            "maintain": counts.get("maintain", 0),
            "no_service": counts.get("no_service", 0),
        },
        "bands": bands_out,
    }
