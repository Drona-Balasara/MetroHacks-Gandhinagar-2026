"""Reusable, deterministic validation for HeadwayIQ datasets.

Validation is driven entirely by the schemas in schema.py so there is one
implementation of each rule. It never discards rows silently: every problem is
reported as an Issue tagged with its dataset, row and field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time

from .schema import Field, Schema


@dataclass
class Issue:
    level: str      # "error" | "warning"
    dataset: str
    row: int        # 1-based row within the file (header excluded); 0 = file-level
    field: str
    message: str

    def __str__(self) -> str:
        where = f"{self.dataset} row {self.row}" if self.row else self.dataset
        col = f".{self.field}" if self.field else ""
        return f"[{self.level.upper()}] {where}{col}: {self.message}"


@dataclass
class ValidationReport:
    inspected: int = 0
    issues: list[Issue] = field(default_factory=list)

    def add(self, level: str, dataset: str, row: int, fld: str, msg: str) -> None:
        self.issues.append(Issue(level, dataset, row, fld, msg))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def invalid_rows(self) -> set[tuple[str, int]]:
        return {(i.dataset, i.row) for i in self.errors if i.row}

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationReport") -> None:
        self.inspected += other.inspected
        self.issues.extend(other.issues)

    def summary(self) -> str:
        bad = len(self.invalid_rows)
        return (
            f"inspected={self.inspected} valid={self.inspected - bad} "
            f"invalid={bad} errors={len(self.errors)} warnings={len(self.warnings)}"
        )


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def parse_value(fld: Field, raw):
    """Parse one raw CSV/JSON value to a Python value, or raise ValueError.

    Blank is returned as None (meaning "unknown"); the caller decides whether a
    blank is allowed. Zero is a real value and is never treated as missing.
    """
    if _is_blank(raw):
        return None
    s = str(raw).strip()
    if fld.kind in ("string", "enum"):
        return s
    if fld.kind == "int":
        v = int(s)                      # rejects "3.5", "abc", "" via ValueError
        return v
    if fld.kind == "float":
        return float(s)
    if fld.kind == "date":
        return date.fromisoformat(s)    # YYYY-MM-DD
    if fld.kind == "time":
        return time.fromisoformat(s)    # HH:MM or HH:MM:SS
    raise ValueError(f"unknown field kind {fld.kind!r}")


def _check_field(rep: ValidationReport, name: str, row: int, fld: Field, raw) -> None:
    if _is_blank(raw):
        if fld.required and not fld.nullable:
            rep.add("error", name, row, fld.name, "required value is missing")
        return
    try:
        value = parse_value(fld, raw)
    except ValueError:
        rep.add("error", name, row, fld.name,
                f"invalid {fld.kind} value {str(raw)!r}")
        return
    if fld.kind == "enum" and value not in fld.allowed:
        rep.add("error", name, row, fld.name,
                f"{value!r} not in allowed values {fld.allowed}")
    if fld.min is not None and isinstance(value, (int, float)) and value < fld.min:
        rep.add("error", name, row, fld.name,
                f"{value} below minimum {fld.min}")
    if fld.max is not None and isinstance(value, (int, float)) and value > fld.max:
        rep.add("error", name, row, fld.name,
                f"{value} above maximum {fld.max}")


def _overlaps(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    return a_start < b_end and b_start < a_end


def validate_dataset(schema: Schema, rows: list[dict], dataset_label: str | None = None) -> ValidationReport:
    """Validate parsed rows (list of column->raw dicts) against a schema."""
    rep = ValidationReport(inspected=len(rows))
    name = dataset_label or schema.name
    seen_pk: dict[str, int] = {}
    bands: dict[tuple, list[tuple]] = {}        # group -> [(start, end, row)]
    declared = {f.name for f in schema.fields}

    for idx, raw_row in enumerate(rows, start=1):
        for col in raw_row:
            if col not in declared:
                rep.add("warning", name, idx, col, "unknown column ignored")

        for fld in schema.fields:
            _check_field(rep, name, idx, fld, raw_row.get(fld.name))

        pk_raw = raw_row.get(schema.pk)
        if not _is_blank(pk_raw):
            key = str(pk_raw).strip()
            if key in seen_pk:
                rep.add("error", name, idx, schema.pk,
                        f"duplicate identifier {key!r} (first seen row {seen_pk[key]})")
            else:
                seen_pk[key] = idx

        if schema.has_time_band:
            try:
                start = parse_value(schema.field("time_band_start"), raw_row.get("time_band_start"))
                end = parse_value(schema.field("time_band_end"), raw_row.get("time_band_end"))
            except ValueError:
                start = end = None
            if start is not None and end is not None:
                if start >= end:
                    rep.add("error", name, idx, "time_band_end",
                            f"time_band_start {start} must precede time_band_end {end}")
                elif schema.nonoverlap_keys:
                    gkey = tuple(str(raw_row.get(k, "")).strip() for k in schema.nonoverlap_keys)
                    for p_start, p_end, p_row in bands.get(gkey, []):
                        if _overlaps(start, end, p_start, p_end):
                            rep.add("error", name, idx, "time_band_start",
                                    f"time band {start}-{end} overlaps row {p_row} "
                                    f"for {dict(zip(schema.nonoverlap_keys, gkey))}")
                    bands.setdefault(gkey, []).append((start, end, idx))
    return rep


def check_referential(child_rows: list[dict], child_field: str, parent_keys: set[str],
                      child_label: str) -> ValidationReport:
    """Report child rows whose foreign key is non-blank but absent from parent_keys."""
    rep = ValidationReport(inspected=len(child_rows))
    for idx, row in enumerate(child_rows, start=1):
        ref = row.get(child_field)
        if not _is_blank(ref) and str(ref).strip() not in parent_keys:
            rep.add("error", child_label, idx, child_field,
                    f"references unknown {child_field}={str(ref).strip()!r}")
    return rep
