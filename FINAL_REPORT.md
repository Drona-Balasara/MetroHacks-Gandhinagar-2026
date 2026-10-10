# HeadwayIQ — Final Implementation Report

**Status: COMPLETE.** The recommendation engine, explainability, demo scenarios
and the Kraken-styled dashboard are built on top of the Phase 1 data foundation.
Everything is deterministic and runs offline (no LLM, no API key, no network, no
cloud). Tests: `python -m pytest -q` → **46 passed**.

## 1. What was added

| File | Purpose |
|---|---|
| `headwayiq/config.py` | All tunable parameters: operating limits, event/weather/holiday multipliers, deadband, demand-level thresholds, planning bands |
| `headwayiq/engine.py` | Deterministic pipeline: `analyse_band` → demand factor → `recommend_band` → `explain`; `generate()` produces the full payload |
| `headwayiq/scenarios.py` | 7 reproducible demo scenarios resolving to engine contexts |
| `headwayiq/server.py` | Localhost, read-only dashboard server (stdlib `http.server`) + JSON API |
| `headwayiq/web/index.html` | Single-page Kraken-styled dashboard (inline CSS/JS, vanilla fetch) |
| `tests/test_engine.py` | 22 engine/scenario tests (logic tested independently of the UI) |

Edited: `cli.py` (`serve` command), `__init__.py` (engine exports), `README.md`.

## 2. The recommendation pipeline

Four small, independently testable steps (see `engine.py`):

1. **Event & weather analysis** — for each corridor and planning band, select
   the events whose corridor **and** time window overlap the band, and the single
   most impactful overlapping weather condition. Missing or uncovered weather is
   reported as a data-quality caveat, never silently treated as clear. Each event
   contributes at most once (no double counting).
2. **Demand estimation** — a synthetic baseline profile is multiplied by a
   **clamped** product of illustrative multipliers (event type, weather, holiday)
   from `config.py`. Baseline, factor and estimated passengers/hour are reported
   separately so the event-driven change is distinct from the baseline.
3. **Headway recommendation** — reference headway (from the **official** GMRC
   timetable) ÷ demand factor, clamped to `[min_headway, max_headway]`, rounded,
   with a deadband around 1.0 so insignificant changes resolve to *maintain*.
   Actions: `increase_frequency`, `reduce_frequency`, `maintain`, `no_service`.
4. **Explanation** — a deterministic template stating the band, the change, the
   drivers (with their multipliers) and the caveats. No LLM.

The timetable is never rewritten by event hours; special-event demand only moves
the recommended headway, keeping operating schedule and recommendation separate.

## 3. Demo scenarios (`python -m headwayiq.cli serve`)

Corridors covered: **NS** and **EW** (both have an official timetable and a
synthetic demand profile). The 05:00–07:00 band is before service starts (NS
06:16, EW 06:20), so it correctly reports *no service*.

| Scenario | Shape of result |
|---|---|
| `normal_weekday` | Steady — all served bands *maintain* 12 min |
| `weekend_leisure` | Steady weekend baseline — *maintain* |
| `stadium_evening` | Evening sports event on NS → *increase* (12 → 8 min) in the 16:00–20:00 and 20:00–23:00 bands |
| `heavy_rain_pm` | Heavy afternoon rain → *increase* in the PM bands |
| `stadium_and_rain` | Event + rain compounded → *increase* across the evening |
| `festival_holiday` | Public holiday damps demand → *reduce* (12 → 15 min); evening festival offsets it to *maintain* |
| `weather_unavailable` | No weather feed → *maintain* with a data-quality caveat on every band |

Covers the required at-least-one shorter-headway (`stadium_evening`) and
at-least-one no-change (`normal_weekday`) cases, plus a longer-headway case.

## 4. Dashboard

`headwayiq/server.py` serves `web/index.html` and two JSON endpoints
(`/api/scenarios`, `/api/recommend?scenario=NAME`) that call the real engine —
no pre-baked output. The page follows `DESIGN-kraken.md`: Kraken Purple
(`#7132f5`) for primary/active and increase actions, green (`#149e61`) for
maintain, cool-gray neutrals for reduce, 12–16px radii, whisper-level shadows,
IBM Plex Sans. States handled: loading (spinner), empty, and error (engine
unreachable / unknown scenario). Each row has an expandable plain-language
explanation. Binds to `127.0.0.1` only, read-only, no secrets — therefore no
auth; it must not be exposed on a public interface without adding access control.

## 5. Data integrity (unchanged guarantees)

- Reference headways remain **official_published** GMRC data; demand stays
  **synthetic**; events/weather stay **manually_entered** — the payload's
  `provenance` block states this on every response.
- Adjustment multipliers are labelled illustrative planning assumptions, not
  measured elasticities. Daily totals are never used as hourly demand; frequency
  is never equated with ridership.
- Recommendations are presented as decision support requiring operator
  validation against live counts.

## 6. Known limitations

- Both Phase-1 corridors are covered: **NS** and **EW** each have an official
  timetable and a demand profile. The EW demand profile is clearly-labelled
  **synthetic** (as is NS); `generate()` iterates every corridor present in both
  the timetable and the demand data, so coverage is data-driven, not hard-coded.
- Planning bands are the five coarse demand bands; a band inherits the reference
  headway covering its start time (so a band straddling a timetable boundary uses
  the earlier headway).
- Multipliers are single global constants per factor; no interaction terms, no
  per-station modelling, no capacity/rolling-stock feasibility check beyond the
  min/max headway clamp.

## 7. Verification

- `python -m pytest -q` → **46 passed** (24 data-foundation + 22 engine).
- `python -m headwayiq.cli validate` → all fixtures valid.
- Dashboard served locally; `/api/scenarios` and `/api/recommend` exercised for
  all 7 scenarios and an unknown-scenario 400 path.
