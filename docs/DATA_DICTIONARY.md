# HeadwayIQ Data Dictionary — Phase 1

The schemas below are enforced in code by `headwayiq/schema.py`; this document
describes them in prose. Types: `string`, `int`, `float`, `date` (`YYYY-MM-DD`),
`time` (`HH:MM`), `enum`. "Nullable" means the value may be left blank to mean
*unknown* — blank is **not** the same as `0`.

## Shared enums

- **data_status** (provenance): `observed`, `official_published`, `synthetic`, `estimated`, `manually_entered`
- **direction**: `northbound`, `southbound`, `eastbound`, `westbound`
- **day_type**: `weekday`, `saturday`, `sunday`, `weekend`, `holiday` (the
  timetable uses `weekday`/`saturday`/`sunday` to match GMRC's published
  distinction; demand profiles use `weekday`/`weekend`)
- **event_type**: `sports`, `festival`, `exam`, `holiday`, `concert`, `other`
- **weather_condition**: `clear`, `clouds`, `rain`, `heavy_rain`, `fog`, `heat`

## timetable — baseline published service (`data/fixtures/timetable.csv`)

| Field | Type | Null | Unit / allowed | Purpose |
|---|---|---|---|---|
| service_id | string | no | unique | Primary key |
| day_type | enum | no | day_type | Which day pattern this row describes |
| line_id | string | no | — | Corridor/line identifier (e.g. `NS`, `EW`) |
| direction | enum | no | direction | Travel direction |
| time_band_start | time | no | HH:MM | Band start (must precede end) |
| time_band_end | time | no | HH:MM | Band end |
| baseline_headway_minutes | float | no | minutes, 0.1–120 | Planned gap between trains |
| source_reference | string | yes | — | Where the value came from |
| data_status | enum | no | provenance | Reliability class |
| notes | string | yes | — | Free text |

Within one `(day_type, line_id, direction)` the time bands must not overlap.

## demand_profile — typical demand (`demand_weekday.csv`, `demand_weekend.csv`)

| Field | Type | Null | Unit / allowed | Purpose |
|---|---|---|---|---|
| profile_id | string | no | unique | Primary key |
| day_type | enum | no | day_type | Day pattern |
| time_band_start | time | no | HH:MM | Band start |
| time_band_end | time | no | HH:MM | Band end |
| direction | enum | no | direction | Travel direction |
| estimated_passengers_per_hour | int | no | passengers/hour, ≥0 | Expected demand in the band |
| station_or_corridor_id | string | yes | — | Scope of the estimate |
| data_status | enum | no | provenance | Reliability class |
| source_reference | string | yes | — | Origin |
| assumptions | string | yes | — | What the number assumes |

Non-overlapping bands within `(day_type, station_or_corridor_id, direction)`.

## event — events and holidays (`events.csv`)

| Field | Type | Null | Unit / allowed | Purpose |
|---|---|---|---|---|
| event_id | string | no | unique | Primary key |
| event_name | string | no | — | Human label |
| event_type | enum | no | event_type | Category |
| event_date | date | no | YYYY-MM-DD | Day of the event |
| start_time | time | yes | HH:MM | Start, if known |
| expected_end_time | time | yes | HH:MM | End, if known |
| venue_or_location | string | yes | — | Where |
| expected_attendance | int | yes | people, 0–5,000,000 | Venue attendance — **not** metro demand |
| affected_corridors_or_stations | string | yes | — | Likely affected lines |
| source_reference | string | yes | — | Origin |
| data_status | enum | no | provenance | Reliability class |
| notes | string | yes | — | Free text |

## weather — observations/forecasts (`weather.csv`)

| Field | Type | Null | Unit / allowed | Purpose |
|---|---|---|---|---|
| weather_id | string | no | unique | Primary key |
| forecast_date | date | no | YYYY-MM-DD | Day |
| time_band_start | time | no | HH:MM | Band start |
| time_band_end | time | no | HH:MM | Band end |
| location | string | no | — | Place |
| temperature_celsius | float | yes | °C, −50–60 | Blank = unknown, not 0 |
| precipitation_mm | float | yes | mm, 0–1000 | Blank = unknown, not 0 |
| weather_condition | enum | no | weather_condition | Summary |
| source_reference | string | yes | — | Origin |
| data_status | enum | no | provenance | Reliability class |
| notes | string | yes | — | Free text |

## Time bands

Time bands are explicit `start`/`end` times, not fixed slots, so each dataset
uses whatever bands its source defines. The **timetable** bands come straight
from the GMRC published frequency rules (see `docs/DATA_SOURCES.md` §6): EW runs
`06:20`–`23:00` split at the peak windows `08:00`–`11:00` and `17:00`–`20:00`;
NS runs `06:16`–`22:00` then `22:00`–`23:00`. The **demand** fixtures use five
coarse bands (`05:00–07:00`, `07:00–10:00`, `10:00–16:00`, `16:00–20:00`,
`20:00–23:00`) — coarse enough to hand-prepare, yet separating peak from
off-peak, which is what later headway calculations need. Because bands are
explicit times, Phase 2/3 may define their own boundaries without a schema
change.
