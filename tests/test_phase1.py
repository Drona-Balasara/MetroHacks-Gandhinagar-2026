"""Phase 1 data-foundation tests. Pure stdlib + pytest; no network, no fixtures DB.

Run: python -m pytest -q
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from headwayiq import db
from headwayiq.schema import PROVENANCE, SCHEMAS
from headwayiq.validation import check_referential, validate_dataset

ROOT = Path(__file__).resolve().parent.parent
INVALID = ROOT / "data" / "fixtures" / "invalid" / "timetable_invalid.csv"


def _rows(dataset: str) -> list[dict]:
    return db.load_fixture_rows(dataset)


# ---- valid fixtures -------------------------------------------------------

def test_all_shipped_fixtures_are_valid():
    for ds, schema in SCHEMAS.items():
        rep = validate_dataset(schema, _rows(ds), ds)
        assert rep.ok, f"{ds} should be valid:\n" + "\n".join(map(str, rep.errors))


def test_report_counts_match_fixture_size():
    rows = _rows("timetable")
    rep = validate_dataset(SCHEMAS["timetable"], rows, "timetable")
    assert rep.inspected == len(rows) and rep.ok and len(rep.invalid_rows) == 0


def test_event_with_unknown_attendance_is_valid():
    rep = validate_dataset(SCHEMAS["event"], _rows("event"), "event")
    assert rep.ok  # EV-2/EV-3/EV-4 have blank expected_attendance


def test_weather_with_missing_measurements_is_valid():
    rep = validate_dataset(SCHEMAS["weather"], _rows("weather"), "weather")
    assert rep.ok  # WX-4 has blank temperature and precipitation


# ---- invalid detection ----------------------------------------------------

def _invalid_report():
    rows = db.read_csv(INVALID)
    return validate_dataset(SCHEMAS["timetable"], rows, "timetable_invalid"), rows


def test_invalid_fixture_is_rejected():
    rep, _ = _invalid_report()
    assert not rep.ok and rep.errors


@pytest.mark.parametrize("needle", [
    "duplicate identifier",       # duplicate service_id
    "overlaps row",               # overlapping time band
    "required value is missing",  # missing day_type
    "below minimum",              # negative headway
    "not in allowed values",      # bad direction + bad data_status enum
    "invalid time value",         # 25:00
    "must precede",               # start >= end
])
def test_invalid_fixture_flags_each_problem(needle):
    rep, _ = _invalid_report()
    assert any(needle in i.message for i in rep.errors), f"missing: {needle}"


def test_negative_passenger_count_rejected():
    rows = [dict(_rows("demand_profile")[0], profile_id="X", estimated_passengers_per_hour="-5")]
    rep = validate_dataset(SCHEMAS["demand_profile"], rows, "d")
    assert not rep.ok and any("below minimum" in i.message for i in rep.errors)


def test_bad_date_format_rejected():
    rows = [dict(_rows("event")[0], event_id="X", event_date="2026/13/40")]
    rep = validate_dataset(SCHEMAS["event"], rows, "e")
    assert any("invalid date" in i.message for i in rep.errors)


def test_zero_precipitation_is_a_value_not_missing():
    rows = [dict(_rows("weather")[0], weather_id="Z", precipitation_mm="0")]
    rep = validate_dataset(SCHEMAS["weather"], rows, "w")
    assert rep.ok  # 0 is accepted, not treated as the (also-valid) blank


def test_referential_integrity():
    good = check_referential([{"line_id": "NS"}], "line_id", {"NS", "EW"}, "c")
    bad = check_referential([{"line_id": "ZZ"}], "line_id", {"NS", "EW"}, "c")
    assert good.ok and not bad.ok


# ---- database -------------------------------------------------------------

def test_init_schema_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_schema(conn)
    db.init_schema(conn)  # second call must not raise
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(SCHEMAS).issubset(tables)
    conn.close()


def test_load_all_and_csv_db_consistency(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_schema(conn)
    db.load_all(conn)
    for ds in SCHEMAS:
        assert db.table_count(conn, ds) == len(_rows(ds))
    row = conn.execute(
        "SELECT baseline_headway_minutes FROM timetable WHERE service_id='TT-EW-EB-WD-3'"
    ).fetchone()
    assert row["baseline_headway_minutes"] == 7  # EW weekday peak, official value
    conn.close()


def test_repeated_load_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_schema(conn)
    db.load_all(conn)
    db.load_all(conn)  # load twice
    assert db.table_count(conn, "timetable") == len(_rows("timetable"))
    conn.close()


def test_load_refuses_invalid_dataset_and_writes_nothing(tmp_path):
    bad_dir = tmp_path / "fx"
    bad_dir.mkdir()
    shutil.copy(INVALID, bad_dir / "timetable.csv")
    conn = db.connect(tmp_path / "t.db")
    db.init_schema(conn)
    with pytest.raises(db.ImportError_):
        db.load_dataset(conn, "timetable", fixture_dir=bad_dir)
    assert db.table_count(conn, "timetable") == 0  # nothing written
    conn.close()


def test_transaction_rolls_back_on_db_error(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_schema(conn)
    sql = ("INSERT INTO timetable (service_id,day_type,line_id,direction,"
           "time_band_start,time_band_end,baseline_headway_minutes,data_status)"
           " VALUES (?,?,?,?,?,?,?,?)")
    with pytest.raises(sqlite3.DatabaseError):
        with conn:  # atomic: both inserts or none
            conn.execute(sql, ("A", "weekday", "NS", "northbound", "07:00", "10:00", 6, "manually_entered"))
            conn.execute(sql, ("B", "weekday", "NS", "northbound", "10:00", "16:00", -1, "manually_entered"))
    assert db.table_count(conn, "timetable") == 0  # first insert rolled back too
    conn.close()


# ---- Phase 1.1: official GMRC timetable provenance ------------------------

def test_timetable_rows_are_official_with_sources():
    for r in _rows("timetable"):
        assert r["data_status"] == "official_published"
        assert "gujaratmetrorail.com" in (r["source_reference"] or "")
        assert r["data_status"] in PROVENANCE


def test_no_synthetic_records_in_official_timetable():
    assert all(r["data_status"] != "synthetic" for r in _rows("timetable"))
    # synthetic demand profiles remain, so the two stay distinguishable
    assert any(r["data_status"] == "synthetic" for r in _rows("demand_profile"))


def test_published_daytypes_and_headways_present():
    rows = _rows("timetable")
    days = {r["day_type"] for r in rows}
    assert {"weekday", "saturday", "sunday"} <= days          # GMRC distinction kept
    ew_peak = [r for r in rows if r["line_id"] == "EW" and r["day_type"] == "weekday"
               and r["time_band_start"] == "08:00"]
    ns_day = [r for r in rows if r["line_id"] == "NS" and r["time_band_start"] == "06:16"]
    assert ew_peak and all(float(r["baseline_headway_minutes"]) == 7 for r in ew_peak)
    assert ns_day and all(float(r["baseline_headway_minutes"]) == 12 for r in ns_day)
