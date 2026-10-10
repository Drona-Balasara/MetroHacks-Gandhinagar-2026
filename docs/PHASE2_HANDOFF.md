# Phase 2 / Phase 3 Integration Contract

Phase 1 gives later phases a validated, typed data layer. Consume it through
the interfaces below — do **not** parse the CSV files or the SQLite rows by
hand, and do not depend on internal field order.

## Stable Python interface

```python
from headwayiq import db, SCHEMAS, validate_dataset

conn = db.connect("data/headwayiq.db")   # or your own path
db.init_schema(conn)                       # idempotent
db.load_all(conn)                          # validates then loads every fixture

rows = db.load_fixture_rows("timetable")   # list[dict] straight from fixtures
rep = validate_dataset(SCHEMAS["demand_profile"], rows)  # ValidationReport
```

- `SCHEMAS[name]` (`timetable`, `demand_profile`, `event`, `weather`) exposes
  the field list, primary key, time-band flag and SQL DDL.
- `data_status` on every row carries provenance — always check it before
  treating a value as real.
- Dates and times are stored as ISO `TEXT`; parse with
  `datetime.date/time.fromisoformat` when you need objects.

## What each phase can retrieve

**Phase 2 (constraints / scenario assembly)** reads:
- `timetable` — baseline headway by `line_id`, `direction`, time band, `day_type`.
- `event` — events and holidays for a target date (`event_date`, `event_type`,
  `expected_attendance` nullable, `affected_corridors_or_stations`).
- `weather` — conditions by `forecast_date` and time band (temperature and
  precipitation nullable).

**Phase 3 (demand estimation / headway calc)** reads:
- `demand_profile` — `estimated_passengers_per_hour` with explicit `day_type`,
  `direction`, time band, `station_or_corridor_id`, `data_status` and
  `assumptions`. Units are passengers **per hour**.

## Guarantees

- Every loaded row passed validation (types, ranges, enums, unique IDs,
  `start < end`, non-overlapping bands, provenance in the allowed set).
- Loads are all-or-nothing per dataset and idempotent (`INSERT OR REPLACE` on
  the primary key); re-running `load_all` never duplicates rows.
- Time bands are explicit start/end times, so Phase 2/3 may define their own
  band boundaries without a schema change.

## Not provided in Phase 1 (do not assume)

Station-level schedules, train-level departures, real ridership, demand→headway
math, any live API, and any attendance→riders mapping. These are later phases.
