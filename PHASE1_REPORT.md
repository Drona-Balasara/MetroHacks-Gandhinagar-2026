# HeadwayIQ — Phase 1 Completion Report

**Phase status: COMPLETE** (data foundation only; Phases 2–3 not started).

## 1. Repository findings

The repository was **empty** (no files, not a git repo, no `CLAUDE.md`, no
existing `design.md`, no prior app, no database). There was nothing to preserve
or extend, so a minimal Python package was established from scratch. The Kraken
design reference was supplied in the task prompt and recorded at
`DESIGN-kraken.md` (repo root).

## 2. Architecture chosen

Standard-library-only Python package + CSV fixtures + SQLite. **No FastAPI, no
frontend, no third-party runtime dependency** — none is needed for a data
foundation, and the "no network / no API key" rule argued against them.
`pytest` is the only dev dependency.

## 3. Files created

| File | Purpose |
|---|---|
| `headwayiq/schema.py` | Declarative schemas, provenance enum, SQLite DDL — single source of truth |
| `headwayiq/validation.py` | Reusable, deterministic validation → `ValidationReport` |
| `headwayiq/db.py` | Fixture loading + SQLite init/load (idempotent, transactional) |
| `headwayiq/cli.py` | `validate` / `init-db` / `load` / `status` commands |
| `headwayiq/__init__.py` | Public interface for Phase 2/3 |
| `data/fixtures/*.csv` | Timetable, weekday+weekend demand, events, weather |
| `data/fixtures/invalid/timetable_invalid.csv` | Broken rows for validation tests |
| `tests/test_phase1.py` | 21 tests |
| `docs/DATA_DICTIONARY.md`, `DATA_SOURCES.md`, `PHASE2_HANDOFF.md`, `DESIGN-kraken.md` | Documentation |
| `README.md`, `pyproject.toml`, `.gitignore` | Project setup |

## 4. Data structures & provenance

Four entities — `timetable`, `demand_profile`, `event`, `weather` — each with a
unique id and a `data_status` provenance field drawn from a fixed set
(`observed`, `official_published`, `synthetic`, `estimated`,
`manually_entered`). Validation and the SQLite DDL are both generated from the
same schema definitions, so rules are written once.

## 5. Dataset inventory

> **Updated in Phase 1.1:** the timetable is now `official_published`,
> transcribed from the GMRC frequency table (effective 2026-05-18) for the EW
> and NS corridors — see `docs/DATA_SOURCES.md` §6. The inventory below is the
> original Phase-1 snapshot.

- **Real / observed / official_published:** none (honest — see `DATA_SOURCES.md`).
- **Manually entered:** timetable (placeholder headways, *not* transcribed from
  the official GMRC timetable), events, weather.
- **Synthetic:** weekday and weekend demand profiles.
- No real GMRC ridership is claimed anywhere; daily totals are explicitly stated
  to not establish hourly station-level demand.

## 6. Validation — actual output

`python -m headwayiq.cli validate` on the shipped fixtures:
```
inspected=48 valid=48 invalid=0 errors=0 warnings=0
Fixtures are READY.
```
The invalid fixture produces 9 errors across 8 rows, each tagged with
dataset/row/field: duplicate id, overlapping band, missing required field,
negative headway (below minimum), invalid direction enum, invalid time value,
invalid provenance enum, and start-not-before-end. Invalid rows are reported,
never silently dropped.

## 7. Testing — actual result

Command: `python -m pytest -q` → **21 passed in ~0.5s**. Coverage includes:
valid records per entity; negative counts; missing values; bad date/time;
duplicate ids; invalid provenance; overlapping bands; event with unknown
attendance; weather with missing measurements; zero-vs-missing distinction;
referential integrity; idempotent schema init; CSV↔DB consistency; repeated
(idempotent) load; refusal to load an invalid dataset (0 rows written); and
transaction rollback on a DB CHECK violation. No pre-existing tests existed, so
there were no regressions to separate.

## 8. Skills & tooling

- **Ponytail (session mode):** active throughout — smallest complete change,
  no speculative abstractions, each new file justified by a Phase 1 requirement.
- `ponytail-audit` / `ponytail-review` were **not** run as separate subagents;
  the surface is small (≈4 modules) and was self-reviewed. They can be run on
  request.
- `frontend-design` and `humanizer` skills are **not installed** in this
  environment, so documentation was written directly. GSAP skills are
  irrelevant to a data phase and were not used.

## 9. Design system

The Kraken reference is recorded at `DESIGN-kraken.md` (colors, typography,
component rules). **No UI was built in Phase 1** — correctly, since this phase
has no user-facing interface. The reference is ready for Phase 2's dashboard.

## 10. Known limitations

- All data is synthetic/placeholder; the timetable is **not** the official GMRC
  schedule and headways are illustrative.
- Demand is network/corridor-level, not station-level; no hourly ridership.
- Load is all-or-nothing per dataset (no partial load) — a deliberate choice to
  keep the DB consistent; revisit if partial import is ever needed.
- Weekend baseline *timetable* is out of scope (weekend *demand* is included).

## 11. Phase 2 handoff

See `docs/PHASE2_HANDOFF.md`. Consume via `headwayiq.db` (`connect`,
`init_schema`, `load_all`, `load_fixture_rows`) and `SCHEMAS`; every row is
pre-validated and carries provenance. Phase 2 gets timetable/events/weather;
Phase 3 gets demand profiles with units, bands, directions and provenance.

## 12. Recommended next action

Begin **Phase 2** by transcribing the real GMRC timetable into `timetable.csv`
with `data_status = official_published` and a real `source_reference`, then
build the constraint/scenario layer against the existing schema. Do not start
Phase 2 implementation without authorization.
