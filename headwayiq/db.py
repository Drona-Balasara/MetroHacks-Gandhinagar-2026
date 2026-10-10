"""Fixture loading and SQLite storage for HeadwayIQ Phase 1.

Schema initialisation is separate from data loading and both are safe to run
repeatedly. Loading a dataset validates first and refuses to touch the database
if any record is invalid, so a failed import never leaves rows half-written.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from .schema import FIXTURES, SCHEMAS, Schema
from .validation import ValidationReport, parse_value, validate_dataset

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "data" / "fixtures"
DEFAULT_DB = ROOT / "data" / "headwayiq.db"


class ImportError_(Exception):
    """Raised when a dataset fails validation and is therefore not loaded."""


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_fixture_rows(dataset: str, fixture_dir: Path = FIXTURE_DIR) -> list[dict]:
    rows: list[dict] = []
    for fname in FIXTURES[dataset]:
        rows.extend(read_csv(fixture_dir / fname))
    return rows


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables. Idempotent (CREATE TABLE IF NOT EXISTS)."""
    for schema in SCHEMAS.values():
        conn.execute(schema.sql)
    conn.commit()


def _row_values(schema: Schema, raw: dict) -> list:
    """Storage values in column order; blank -> None (SQL NULL).

    Dates/times are kept as their original ISO strings (stored as TEXT); numbers
    are parsed to int/float. Validation runs before this, so values are sound.
    """
    out = []
    for fld in schema.fields:
        v = raw.get(fld.name)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            out.append(None)
        elif fld.kind in ("int", "float"):
            try:
                out.append(parse_value(fld, v))
            except ValueError:
                out.append(v)               # let the DB CHECK/typing reject it
        else:
            out.append(str(v).strip())      # string/enum/date/time stored as TEXT
    return out


def load_dataset(conn: sqlite3.Connection, dataset: str,
                 fixture_dir: Path = FIXTURE_DIR) -> ValidationReport:
    """Validate and load one dataset in a single transaction.

    Returns the validation report. Raises ImportError_ without writing anything
    when validation fails, so the database is never left inconsistent.
    """
    schema = SCHEMAS[dataset]
    rows = load_fixture_rows(dataset, fixture_dir)
    report = validate_dataset(schema, rows, dataset_label=dataset)
    if not report.ok:
        raise ImportError_(
            f"{dataset}: {len(report.errors)} error(s); refusing to load.\n"
            + "\n".join(str(i) for i in report.errors)
        )

    cols = [f.name for f in schema.fields]
    placeholders = ", ".join("?" for _ in cols)
    # INSERT OR REPLACE keyed on the primary key -> repeated loads are idempotent
    # and never duplicate fixture records.
    sql = f"INSERT OR REPLACE INTO {dataset} ({', '.join(cols)}) VALUES ({placeholders})"
    try:
        with conn:  # transaction: commits on success, rolls back on exception
            conn.executemany(sql, [tuple(_row_values(schema, r)) for r in rows])
    except sqlite3.DatabaseError as exc:
        raise ImportError_(f"{dataset}: database rejected import ({exc}); rolled back") from exc
    return report


def load_all(conn: sqlite3.Connection, fixture_dir: Path = FIXTURE_DIR) -> dict[str, ValidationReport]:
    return {ds: load_dataset(conn, ds, fixture_dir) for ds in SCHEMAS}


def table_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
