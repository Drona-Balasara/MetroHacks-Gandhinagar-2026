"""Engine tests: event/weather analysis, demand estimation, headway logic and
the demo scenarios. Pure stdlib + pytest; no network, no DB, no UI.

Run: python -m pytest -q
"""
from __future__ import annotations

from headwayiq import scenarios
from headwayiq.config import DEFAULT, Config
from headwayiq.engine import (analyse_band, generate, recommend_band,
                              reference_bands, resolve_day_type)

CFG = DEFAULT


# ---- recommend_band -------------------------------------------------------

def test_no_reference_headway_is_no_service():
    assert recommend_band(None, 1.5, CFG) == (None, "no_service")


def test_demand_in_deadband_maintains_reference():
    assert recommend_band(12, 1.0, CFG) == (12, "maintain")
    assert recommend_band(12, 1.1, CFG) == (12, "maintain")   # within deadband_high


def test_high_demand_shortens_headway():
    rec, action = recommend_band(12, 1.5, CFG)
    assert action == "increase_frequency" and rec == 8.0      # 12/1.5, rounded to 0.5


def test_low_demand_lengthens_headway():
    rec, action = recommend_band(12, 0.8, CFG)
    assert action == "reduce_frequency" and rec == 15.0       # 12/0.8


def test_recommendation_respects_min_and_max_limits():
    assert recommend_band(12, 10.0, CFG)[0] == CFG.min_headway   # clamped down
    assert recommend_band(12, 0.1, CFG)[0] == CFG.max_headway    # clamped up


# ---- analyse_band ---------------------------------------------------------

def _sports(corridors, start="19:30", end="23:00"):
    return {"event_id": "E", "event_name": "match", "event_type": "sports",
            "affected_corridors_or_stations": corridors, "start_time": start,
            "expected_end_time": end}


def test_event_applies_only_to_affected_corridor_and_overlapping_band():
    ev = [_sports("NS")]
    f_evening, sig, _ = analyse_band("NS", ("16:00", "20:00"), ev, [], False, CFG)
    f_morning, _, _ = analyse_band("NS", ("07:00", "10:00"), ev, [], False, CFG)
    f_other, _, _ = analyse_band("EW", ("16:00", "20:00"), ev, [], False, CFG)
    assert f_evening == CFG.event_factor["sports"] and sig[0]["kind"] == "event"
    assert f_morning == 1.0        # event window does not overlap the morning band
    assert f_other == 1.0          # wrong corridor


def test_weather_takes_single_most_impactful_overlapping_condition():
    wx = [{"weather_id": "a", "time_band_start": "16:00", "time_band_end": "20:00", "weather_condition": "rain"},
          {"weather_id": "b", "time_band_start": "17:00", "time_band_end": "19:00", "weather_condition": "heavy_rain"}]
    f, sig, _ = analyse_band("NS", ("16:00", "20:00"), [], wx, False, CFG)
    assert f == CFG.weather_factor["heavy_rain"] and len([s for s in sig if s["kind"] == "weather"]) == 1


def test_missing_weather_is_reported_not_assumed_clear():
    _, _, w_none = analyse_band("NS", ("07:00", "10:00"), [], None, False, CFG)
    _, _, w_gap = analyse_band("NS", ("07:00", "10:00"), [], [], False, CFG)
    assert w_none and w_gap        # both carry a data-quality warning


def test_holiday_damps_and_factor_is_clamped():
    f, sig, _ = analyse_band("NS", ("07:00", "10:00"), [], [], True, CFG)
    assert f == CFG.holiday_factor and any(s["kind"] == "holiday" for s in sig)
    # cumulative clamp: a wild config cannot explode demand past the cap
    big = Config(event_factor={"sports": 10.0, "other": 1.0})
    f2, _, _ = analyse_band("NS", ("16:00", "20:00"), [_sports("NS")], [], False, big)
    assert f2 == big.cumulative_max


# ---- generate -------------------------------------------------------------

def test_generate_marks_pre_service_band_as_no_service():
    ctx = {"day_type": "weekday", "events": [], "weather": scenarios.CLEAR}
    p = generate(ctx)
    early = [b for b in p["bands"] if b["band_start"] == "05:00"]
    assert early and all(b["action"] == "no_service" for b in early)   # NS starts 06:16


def test_generate_estimated_demand_is_baseline_times_factor():
    p = scenarios.run("stadium_evening")
    b = next(x for x in p["bands"]
             if x["direction"] == "northbound" and x["band_start"] == "16:00")
    assert b["estimated_pph"] == round(b["baseline_pph"] * b["demand_factor"])


def test_generate_is_deterministic():
    assert generate(scenarios.context("stadium_and_rain")) == \
           generate(scenarios.context("stadium_and_rain"))


def test_provenance_keeps_timetable_official_and_demand_synthetic():
    prov = scenarios.run("normal_weekday")["provenance"]
    assert "official_published" in prov["timetable"] and "synthetic" in prov["demand"]


# ---- scenarios ------------------------------------------------------------

def test_all_seven_scenarios_run_and_are_listed():
    names = [s["name"] for s in scenarios.list_scenarios()]
    assert len(names) == 7
    for n in names:
        assert scenarios.run(n)["bands"]


def test_scenarios_cover_increase_reduce_and_no_change():
    assert scenarios.run("stadium_evening")["summary"]["increase_frequency"] > 0
    assert scenarios.run("festival_holiday")["summary"]["reduce_frequency"] > 0
    nw = scenarios.run("normal_weekday")["summary"]
    assert nw["increase_frequency"] == 0 and nw["reduce_frequency"] == 0  # steady day


def test_weather_unavailable_scenario_flags_the_gap():
    p = scenarios.run("weather_unavailable")
    assert any(b["warnings"] for b in p["bands"])


def test_resolve_day_type_matches_calendar():
    assert resolve_day_type("2026-10-17") == "saturday"   # a Saturday
    assert resolve_day_type("2026-10-13") == "weekday"     # a Tuesday


def test_reference_bands_come_from_official_timetable():
    bands = reference_bands(__import__("headwayiq.db", fromlist=["x"]).load_fixture_rows("timetable"),
                            "NS", "northbound", "weekday")
    assert bands and bands[0][2] == 12.0   # NS daytime headway, official value


# ---- corridor coverage (EW) ----------------------------------------------

def test_both_corridors_are_covered():
    corridors = scenarios.run("normal_weekday")["corridors"]
    assert corridors == ["EW", "NS"]       # both have official timetable + demand


def test_ew_demand_is_labelled_synthetic():
    demand = __import__("headwayiq.db", fromlist=["x"]).load_fixture_rows("demand_profile")
    ew = [r for r in demand if r["station_or_corridor_id"] == "EW"]
    assert ew and all(r["data_status"] == "synthetic" for r in ew)


def test_ew_uses_its_own_varying_official_headways():
    # EW weekday reference headways differ across bands (7 peak / 10 off-peak),
    # unlike NS's flat 12 — confirms per-corridor timetable lookup.
    p = scenarios.run("normal_weekday")
    ew = {b["band_start"]: b["reference_headway_min"]
          for b in p["bands"] if b["line"] == "EW" and b["direction"] == "eastbound"}
    assert ew["10:00"] == 7.0 and ew["07:00"] == 10.0


def test_ns_only_event_does_not_change_ew():
    p = scenarios.run("stadium_evening")   # EV-1 affects corridor NS only
    ew = [b for b in p["bands"] if b["line"] == "EW"]
    assert all(b["action"] in ("maintain", "no_service") for b in ew)
