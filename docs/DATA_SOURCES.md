# Data Source Register, Assumptions & Limitations

## 1. Honesty statement (read first)

**The baseline timetable (`timetable.csv`) is now transcribed from the official
GMRC published frequency table (`official_published`, see §6). All *demand*,
*event* and *weather* fixtures remain synthetic or hand-prepared** — they
exercise the schema so Phase 2/3 can be built against a stable shape, and they
are **not evidence of actual passenger demand**.

A publicly reported *daily* passenger-journey total (the kind GMRC publishes in
annual reports) does **not** establish *station-level, hourly, by-direction*
demand. The official timetable gives service *frequency*, not *ridership* —
knowing trains run every 7 minutes says nothing about how many passengers board.
Converting either into the hourly, directional demand profile this system needs
requires assumptions Phase 1 does not have grounds to make. That conversion is a
Phase 3 modelling problem, not a data fact.

## 2. Source register

| Dataset | File | Provenance (`data_status`) | How prepared | Known limitation |
|---|---|---|---|---|
| Baseline timetable | `timetable.csv` | `official_published` | Transcribed from GMRC published frequency table, effective 2026-05-18 (see §6) | Covers Phase-1 corridors EW & NS only; frequency, not ridership; not direction-specific |
| Weekday demand | `demand_weekday.csv` | `synthetic` | Invented commuter-shaped profile (AM/PM peaks), NS and EW corridors | No empirical basis; illustrative shape only |
| Weekend demand | `demand_weekend.csv` | `synthetic` | Invented leisure-shaped profile (midday high), NS and EW corridors | No empirical basis; illustrative shape only |
| Events / holidays | `events.csv` | `manually_entered` | Scenario rows: a stadium match, a festival, a public holiday, an exam day | Illustrative dates/attendances; attendance left blank where genuinely unknown |
| Weather | `weather.csv` | `manually_entered` | Scenario rows: clear, hot, heavy-rain, and an unknown-measurement row | Not a live or historical forecast |
| Invalid sample | `invalid/timetable_invalid.csv` | n/a | Deliberately broken rows for validation tests | Never loaded into the database |

Demand/event/weather fixtures claim no source URLs or real measurements, because
none were used. The timetable's official source is recorded in §6.

## 3. Provenance model

`data_status` classifies every record (see the data dictionary enum). The
intent:

- `observed` / `official_published` — may be used to *validate* a forecast.
- `synthetic` / `estimated` / `manually_entered` — demonstration only; must
  never be used to claim real-world accuracy.

The timetable is `official_published`; demand/event/weather remain
demonstration classes. All four "trustworthy" vs "demonstration" classes exist
in the schema so more real data slots in later without a schema change.

## 4. Key assumptions baked into the fixtures

- Two corridors (`NS`, `EW`) and four directions are enough to prove the model
  handles more than one frequency; the real network has more.
- Attendance is a venue figure, never a metro-demand figure. Any mapping from
  attendance to riders is deferred to Phase 3.
- `precipitation_mm = 0` means an observed dry band; **missing** precipitation
  is left blank, never zero.

## 5. What real data would be needed to validate the eventual system

1. The official GMRC timetable (headway by line/direction/time band).
2. Hourly, directional ridership (gate/AFC counts), not just daily totals.
3. Historical event calendars paired with the demand actually observed.
4. Historical weather paired with the demand actually observed.

Until those exist, forecasts built on these fixtures are illustrative only.

## 6. Phase 1.1 — official GMRC timetable transcription

- **Source title:** "Ahmedabad Metro Rail Project — Train Frequency, Departure
  of First & Last Train, Travel Time/Distance w.e.f 18.05.2026".
- **Source URL:** https://www.gujaratmetrorail.com/ahmedabad/train-information/
  (frequency table image `Revised-Time-Table-on-18.05.2026updated.jpg`).
- **Retrieved:** 2026-10-10.
- **Published effective date:** 2026-05-18 (recorded in each row's `notes`).
- **Coverage transcribed:** Phase-1 corridors only —
  **Line-1 EW** (Vastral Gam ↔ Thaltej Gam) and **Line-2 NS** (APMC ↔ Koteshwar
  Road). 46 rows = EW {weekday 7 bands, saturday 7, sunday 3} + NS {2 bands} ×
  weekday/saturday/sunday, each × 2 directions.
- **Fields transcribed:** `line_id`, `direction`, `day_type`,
  `time_band_start/end`, `baseline_headway_minutes`, with
  `data_status=official_published` and the source URL in `source_reference`.
- **Transcription method:** the published frequency table is an image. It was
  downloaded and read directly (not from search snippets), and the frequency
  *rules* were expanded into contiguous, non-overlapping time-band rows the
  schema requires. The expansion script is not committed; values were verified
  against the image and by `validate_dataset`.
- **GMRC frequency rules captured.** EW: weekday peak (08:00–11:00 &
  17:00–20:00) 7 min; weekday off-peak & Saturday peak 10 min; Saturday
  off-peak & Sunday full-day 12 min; all-days 06:20–07:00 & 22:00–23:00 20 min.
  NS: Monday–Sunday 06:16–22:00 12 min, 22:00–23:00 20 min. The schema's
  single-band rows forced `day_type` to gain `saturday`/`sunday` so the GMRC
  weekday/Saturday/Sunday distinction is preserved rather than flattened.

### Known omissions, ambiguities and remaining synthetic data

- **Phase-2 corridors NOT transcribed:** Line-3 (Koteshwar Road ↔ Mahatma
  Mandir) and Line-4 (GNLU ↔ GIFT City). Reasons: their published frequencies
  are stated as an *"Average N minutes"* (irregular, not a fixed headway),
  Line-4 includes a midday *bus-only* substitution and partial-day operation,
  and the source states no cardinal direction for them — representing them would
  mean inventing values. They are verified to exist and are left for a later
  pass once the schema can hold "average/irregular" and non-cardinal directions.
- **Direction not published per-direction:** GMRC gives one frequency per line.
  Both directions are stored with the same headway; each row's `notes` records
  "published frequency is not direction-specific".
- **Station-level departure times** (the second GMRC image) are deliberately
  **not** encoded — the schema is corridor/band level and inventing per-train
  departures is out of scope.
- **Remaining synthetic/manually-entered records:** 0 synthetic timetable rows;
  all 40 demand rows stay `synthetic` (NS and EW corridors, weekday + weekend);
  all event/weather rows stay `manually_entered`. Timetable and demand
  provenance remain distinguishable.
- **Frequency ≠ demand.** The official timetable establishes service supply, not
  passenger counts, and cannot by itself establish hourly station-level demand.
