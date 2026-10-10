"""HeadwayIQ Phase 1 CLI.

Usage:
    python -m headwayiq.cli validate            # validate fixtures only (no DB)
    python -m headwayiq.cli init-db [DB_PATH]   # create tables (idempotent)
    python -m headwayiq.cli load [DB_PATH]      # init + validate + load fixtures
    python -m headwayiq.cli status [DB_PATH]    # dataset readiness report
    python -m headwayiq.cli serve [PORT]        # run the local dashboard (default 8000)
"""
from __future__ import annotations

import sys
from pathlib import Path

from .db import (DEFAULT_DB, FIXTURE_DIR, ImportError_, connect, init_schema,
                 load_dataset, load_fixture_rows, table_count)
from .schema import SCHEMAS
from .validation import ValidationReport, validate_dataset


def _validate_all() -> ValidationReport:
    combined = ValidationReport()
    for ds, schema in SCHEMAS.items():
        rows = load_fixture_rows(ds)
        combined.merge(validate_dataset(schema, rows, dataset_label=ds))
    return combined


def _print_report(rep: ValidationReport) -> None:
    print(rep.summary())
    for issue in rep.issues:
        print("  " + str(issue))


def cmd_validate() -> int:
    rep = _validate_all()
    _print_report(rep)
    print("\nFixtures are READY." if rep.ok else "\nFixtures have ERRORS; not ready to load.")
    return 0 if rep.ok else 1


def cmd_init_db(db: Path) -> int:
    with connect(db) as conn:
        init_schema(conn)
    print(f"Initialised schema in {db}")
    return 0


def cmd_load(db: Path) -> int:
    conn = connect(db)
    init_schema(conn)
    rc = 0
    for ds in SCHEMAS:
        try:
            rep = load_dataset(conn, ds)
            print(f"loaded {ds}: {rep.summary()}")
        except ImportError_ as exc:
            print(f"FAILED {ds}: {exc}")
            rc = 1
    conn.close()
    return rc


def cmd_status(db: Path) -> int:
    val = _validate_all()
    print("Fixture validation:", val.summary())
    if db.exists():
        conn = connect(db)
        print(f"\nDatabase {db}:")
        for ds in SCHEMAS:
            try:
                print(f"  {ds}: {table_count(conn, ds)} rows")
            except Exception as exc:  # table may not exist yet
                print(f"  {ds}: not initialised ({exc})")
        conn.close()
    else:
        print(f"\nDatabase {db} not created yet (run 'load').")
    return 0 if val.ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "status"
    db = Path(argv[1]) if len(argv) > 1 else DEFAULT_DB
    if cmd == "validate":
        return cmd_validate()
    if cmd == "init-db":
        return cmd_init_db(db)
    if cmd == "load":
        return cmd_load(db)
    if cmd == "status":
        return cmd_status(db)
    if cmd == "serve":
        from .server import serve
        serve(port=int(argv[1]) if len(argv) > 1 else 8000)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
