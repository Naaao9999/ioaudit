"""Read-only diagnostics for delimited text files.

This module deliberately stops at the file boundary.  It does not identify
which rows/columns form an IO table and it does not repair or normalize data.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field, fields, is_dataclass
import io
import json
from pathlib import Path
import re
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .exceptions import IOValidationError


_DELIMITER_CANDIDATES = (",", ";", "\t", "|")
_MISSING_TOKENS = frozenset({"", "NA", "N/A", "na", "n/a", "NULL", "null", "-", "－", "…", "..."})
_NAN_INF_TOKENS = frozenset({"nan", "NaN", "NAN", "inf", "Inf", "INF", "infinity", "Infinity", "-inf", "+inf"})
_NUMBER_RE = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$")
_THOUSANDS_RE = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+$")
_DECIMAL_COMMA_RE = re.compile(r"^[+-]?\d+,\d+$")
_INVISIBLE = {
    "\ufeff": "BOM",
    "\u200b": "ZERO_WIDTH_SPACE",
    "\u200c": "ZERO_WIDTH_NON_JOINER",
    "\u200d": "ZERO_WIDTH_JOINER",
    "\u00a0": "NO_BREAK_SPACE",
}


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    return value


def _flatten(value: Any, prefix: str, rows: list[dict[str, Any]]) -> None:
    if is_dataclass(value):
        for field in fields(value):
            _flatten(getattr(value, field.name), f"{prefix}.{field.name}" if prefix else field.name, rows)
    elif isinstance(value, dict):
        for key, item in value.items():
            _flatten(item, f"{prefix}.{key}" if prefix else str(key), rows)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _flatten(item, f"{prefix}[{index}]", rows)
    else:
        rows.append({"path": prefix, "value": value})


@dataclass
class CSVInspectionReport:
    """Machine-readable, read-only diagnostics for one delimited file."""

    path: str
    status: str = "SKIPPED"
    encoding: str | None = None
    bom: bool = False
    delimiter: str | None = None
    delimiter_requested: str | None = None
    delimiter_candidates: dict[str, int] = field(default_factory=dict)
    blank_lines: list[int] = field(default_factory=list)
    internal_blank_lines: list[int] = field(default_factory=list)
    trailing_blank_lines: list[int] = field(default_factory=list)
    completely_blank_rows: list[int] = field(default_factory=list)
    inconsistent_column_count: list[dict[str, int]] = field(default_factory=list)
    expected_column_count: int | None = None
    header_line: int | None = None
    preamble_rows: list[int] = field(default_factory=list)
    header_continuation_rows: list[int] = field(default_factory=list)
    trailing_delimiter: list[int] = field(default_factory=list)
    duplicate_headers: list[str] = field(default_factory=list)
    empty_headers: list[int] = field(default_factory=list)
    leading_empty_headers: list[int] = field(default_factory=list)
    whitespace: list[dict[str, Any]] = field(default_factory=list)
    quoting_anomaly: bool = False
    quoting_error: str | None = None
    quoting_error_line: int | None = None
    possible_unquoted_thousands_separator: bool = False
    thousands_separator_tokens: dict[str, int] = field(default_factory=dict)
    decimal_convention: dict[str, Any] = field(default_factory=dict)
    numeric_columns: dict[str, dict[str, Any]] = field(default_factory=dict)
    non_numeric_tokens: dict[str, int] = field(default_factory=dict)
    missing_value_tokens: dict[str, int] = field(default_factory=dict)
    nan_inf_like_tokens: dict[str, int] = field(default_factory=dict)
    unexpected_text_rows: list[dict[str, Any]] = field(default_factory=list)
    repeated_header_rows: list[int] = field(default_factory=list)
    completely_blank_columns: list[dict[str, Any]] = field(default_factory=list)
    invisible_characters: list[dict[str, Any]] = field(default_factory=list)
    parse_error: str | None = None
    parse_error_line: int | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible report dictionary."""

        return _jsonable(self)

    def to_json(self, **kwargs: Any) -> str:
        """Serialize the report to JSON."""

        options = {"ensure_ascii": False, "indent": 2, "sort_keys": True}
        options.update(kwargs)
        return json.dumps(self.to_dict(), **options)

    def to_dataframe(self) -> pd.DataFrame:
        """Return flattened ``path``/``value`` diagnostics."""

        rows: list[dict[str, Any]] = []
        _flatten(self.to_dict(), "", rows)
        return pd.DataFrame(rows, columns=["path", "value"])

    def summary(self) -> str:
        """Return a concise human-readable file diagnostic summary."""

        lines = [
            "File Diagnostics",
            "================",
            f"Status                   {self.status}",
            f"Encoding                 {self.encoding or 'SKIPPED'}",
            f"BOM                      {'YES' if self.bom else 'NO'}",
            f"Delimiter                {repr(self.delimiter) if self.delimiter else 'SKIPPED'}",
            f"Blank lines              {len(self.blank_lines)}",
            f"Column-count anomalies   {len(self.inconsistent_column_count)}",
            f"Quoting anomaly          {'YES' if self.quoting_anomaly else 'NO'}",
            f"Numeric columns          {len(self.numeric_columns)}",
            f"Unexpected numeric text  {sum(self.non_numeric_tokens.values())}",
        ]
        return "\n".join(lines)


def _decode(raw: bytes, requested: str | None) -> tuple[str, str, bool]:
    bom_encodings = (
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    )
    bom = False
    detected = None
    for marker, encoding in bom_encodings:
        if raw.startswith(marker):
            bom = True
            detected = encoding
            break
    candidates = [requested] if requested else ([detected] if detected else []) + ["utf-8", "cp932"]
    tried: list[str] = []
    for encoding in candidates:
        if not encoding or encoding in tried:
            continue
        tried.append(encoding)
        try:
            return raw.decode(encoding), encoding, bom
        except (UnicodeDecodeError, LookupError):
            continue
    raise IOValidationError(
        f"could not decode {len(raw)} bytes; tried encodings: {', '.join(tried) or 'none'}"
    )


def _detect_delimiter(text: str) -> tuple[str | None, dict[str, int]]:
    lines = text.splitlines()
    counts = {
        delimiter: sum(line.count(delimiter) for line in lines if line.strip())
        for delimiter in _DELIMITER_CANDIDATES
    }
    positive = {key: value for key, value in counts.items() if value > 0}
    if not positive:
        return None, counts
    scores: dict[str, tuple[int, float, int, int, int]] = {}
    for delimiter in positive:
        try:
            reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=False)
            rows = [row for row in reader if row and any(cell.strip() for cell in row)]
            widths = Counter(len(row) for row in rows)
            modal_width, modal_count = widths.most_common(1)[0] if widths else (1, 0)
            consistency = modal_count / len(rows) if rows else 0.0
            scores[delimiter] = (
                int(modal_width > 1),
                consistency,
                modal_width,
                counts[delimiter],
                int(delimiter == ","),
            )
        except (csv.Error, TypeError):
            scores[delimiter] = (0, 0.0, 1, counts[delimiter], int(delimiter == ","))
    return max(positive, key=lambda key: scores[key]), counts


def _header_key(header: str, index: int, used: set[str]) -> str:
    base = header.strip() or f"<empty:{index + 1}>"
    key = base
    counter = 2
    while key in used:
        key = f"{base}[{counter}]"
        counter += 1
    used.add(key)
    return key


def _record_token(
    report: CSVInspectionReport,
    token: str,
    column_key: str,
    line_number: int,
    column_index: int,
) -> tuple[bool, bool]:
    stripped = token.strip()
    missing = stripped in _MISSING_TOKENS
    if missing:
        report.missing_value_tokens[stripped] = report.missing_value_tokens.get(stripped, 0) + 1
        return True, False
    if stripped in _NAN_INF_TOKENS:
        report.nan_inf_like_tokens[stripped] = report.nan_inf_like_tokens.get(stripped, 0) + 1
        report.non_numeric_tokens[stripped] = report.non_numeric_tokens.get(stripped, 0) + 1
        return False, True
    if _THOUSANDS_RE.fullmatch(stripped):
        report.thousands_separator_tokens[stripped] = report.thousands_separator_tokens.get(stripped, 0) + 1
        return False, False
    if _NUMBER_RE.fullmatch(stripped):
        return False, False
    if stripped:
        report.non_numeric_tokens[stripped] = report.non_numeric_tokens.get(stripped, 0) + 1
    return False, bool(stripped)


def _status(report: CSVInspectionReport) -> str:
    critical = bool(
        report.parse_error
        or report.quoting_anomaly
        or report.inconsistent_column_count
        or report.duplicate_headers
        or any(index != 0 for index in report.empty_headers)
    )
    warning = bool(
        report.blank_lines
        or report.trailing_delimiter
        or report.whitespace
        or report.possible_unquoted_thousands_separator
        or report.non_numeric_tokens
        or report.completely_blank_rows
        or report.unexpected_text_rows
        or report.repeated_header_rows
        or report.invisible_characters
        or report.leading_empty_headers
    )
    return "FAIL" if critical else ("WARNING" if warning else "PASS")


def _dominant_width(data_rows: Sequence[tuple[int, list[str]]]) -> int:
    """Return the most representative width for a nonblank CSV body.

    Title and note rows are often one-column rows in otherwise rectangular
    files.  Prefer the most frequent multi-column width when one exists, and
    fall back to the first nonblank row for genuinely one-column files.
    """

    widths = Counter(len(row) for _, row in data_rows)
    multi_column = [(width, count) for width, count in widths.items() if width > 1]
    if multi_column:
        return max(multi_column, key=lambda item: (item[1], item[0]))[0]
    return len(data_rows[0][1])


def _looks_like_header_continuation(row: Sequence[str], width: int) -> bool:
    """Identify a likely descriptive header row without extracting table data."""

    if len(row) != width or width < 2 or row[0].strip():
        return False
    text_tokens = 0
    for token in row[1:]:
        stripped = token.strip()
        if (
            not _NUMBER_RE.fullmatch(stripped)
            and not _THOUSANDS_RE.fullmatch(stripped)
            and stripped not in _MISSING_TOKENS
            and stripped not in _NAN_INF_TOKENS
        ):
            text_tokens += 1
    return text_tokens >= max(2, int(0.75 * (width - 1)))


def inspect_csv(
    path: str | Path,
    delimiter: str | None = ",",
    encoding: str | None = None,
) -> CSVInspectionReport:
    """Inspect a CSV/delimited file without repairing or extracting an IO table.

    Parameters
    ----------
    path:
        File path to inspect.
    delimiter:
        One-character delimiter.  Pass ``None`` for a small deterministic
        candidate comparison among comma, semicolon, tab, and pipe.
    encoding:
        Explicit Python codec name.  If omitted, BOM, UTF-8, and CP932 are
        tried in that order.
    """

    if delimiter is not None and (not isinstance(delimiter, str) or len(delimiter) != 1):
        raise IOValidationError("delimiter must be one character or None")
    try:
        file_path = Path(path)
        raw = file_path.read_bytes()
    except (OSError, TypeError, ValueError) as exc:
        raise IOValidationError(f"could not read CSV file {path!r}: {exc}") from exc

    text, used_encoding, bom = _decode(raw, encoding)
    physical_lines = text.splitlines()
    used_delimiter, candidate_counts = _detect_delimiter(text)
    chosen_delimiter = delimiter if delimiter is not None else used_delimiter
    report = CSVInspectionReport(
        path=str(file_path),
        encoding=used_encoding,
        bom=bom,
        delimiter=chosen_delimiter,
        delimiter_requested=delimiter,
        delimiter_candidates=candidate_counts,
    )
    if chosen_delimiter is None:
        report.notes.append("No delimiter candidate was detected")
        report.status = "SKIPPED"
        return report

    for line_number, line in enumerate(physical_lines, start=1):
        if not line.strip():
            report.blank_lines.append(line_number)
            report.completely_blank_rows.append(line_number)
        if line.rstrip("\r\n").endswith(chosen_delimiter):
            report.trailing_delimiter.append(line_number)
        for char, name in _INVISIBLE.items():
            if char in line:
                report.invisible_characters.append(
                    {"line": line_number, "character": f"U+{ord(char):04X}", "name": name}
                )
    nonblank_lines = [line_number for line_number, line in enumerate(physical_lines, start=1) if line.strip()]
    if report.blank_lines and nonblank_lines:
        last_nonblank = max(nonblank_lines)
        report.internal_blank_lines = [line for line in report.blank_lines if line < last_nonblank]
        report.trailing_blank_lines = [line for line in report.blank_lines if line > last_nonblank]

    rows: list[tuple[int, list[str]]] = []
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=chosen_delimiter, strict=True)
        for row in reader:
            rows.append((reader.line_num, row))
    except csv.Error as exc:
        report.quoting_anomaly = True
        report.parse_error = str(exc)
        report.quoting_error = str(exc)
        report.quoting_error_line = getattr(reader, "line_num", None)
        report.parse_error_line = report.quoting_error_line
        # A permissive second pass is used only to continue diagnostics.  Its
        # output is never written back and the strict parsing error remains in
        # the report.
        try:
            reader = csv.reader(io.StringIO(text, newline=""), delimiter=chosen_delimiter, strict=False)
            rows = [(reader.line_num, row) for row in reader]
        except csv.Error:
            rows = []

    for line_number, row in rows:
        if row and not any(cell.strip() for cell in row) and line_number not in report.completely_blank_rows:
            report.completely_blank_rows.append(line_number)
    report.completely_blank_rows.sort()
    data_rows = [(line, row) for line, row in rows if row and any(cell.strip() for cell in row)]
    if not data_rows:
        report.status = "SKIPPED"
        report.notes.append("No nonblank CSV rows were found")
        return report
    report.expected_column_count = _dominant_width(data_rows)
    header_position = next(
        index
        for index, (_, row) in enumerate(data_rows)
        if len(row) == report.expected_column_count
    )
    header_line, header = data_rows[header_position]
    report.header_line = header_line
    report.preamble_rows = [
        line_number
        for line_number, _ in data_rows[:header_position]
    ]
    used_headers: set[str] = set()
    header_keys: list[str] = []
    normalized_headers: list[str] = []
    for index, value in enumerate(header):
        normalized = value.strip()
        normalized_headers.append(normalized)
        header_keys.append(_header_key(value, index, used_headers))
        if not normalized:
            report.empty_headers.append(index)
            if index == 0:
                # A blank leading stub column is common in exported tables:
                # it holds row labels while the remaining fields are the
                # rectangular header.  Keep the evidence but do not treat it
                # like an unnamed data column in the critical gate.
                report.leading_empty_headers.append(index)
    counts = Counter(normalized_headers)
    report.duplicate_headers = sorted(name for name, count in counts.items() if name and count > 1)

    all_rows_for_columns = [row for _, row in rows]
    for line_number, row in data_rows:
        if line_number < header_line:
            # A title or source row before the first rectangular row is file
            # preamble, not a malformed table record.
            continue
        if len(row) != report.expected_column_count:
            if len(row) == 1:
                text = row[0].strip()
                if text:
                    report.unexpected_text_rows.append({"line": line_number, "text": text})
                continue
            report.inconsistent_column_count.append(
                {"line": line_number, "expected": report.expected_column_count, "actual": len(row)}
            )
        if (
            len(row) == report.expected_column_count
            and [cell.strip() for cell in row] == normalized_headers
            and line_number != header_line
        ):
            report.repeated_header_rows.append(line_number)
        if len(row) == report.expected_column_count and _looks_like_header_continuation(
            row, report.expected_column_count
        ):
            report.header_continuation_rows.append(line_number)
        for index, token in enumerate(row):
            if token != token.strip():
                report.whitespace.append(
                    {"line": line_number, "column": index, "value": token}
                )

    if report.expected_column_count and report.inconsistent_column_count:
        for line_number, row in data_rows:
            if len(row) > report.expected_column_count and chosen_delimiter == ",":
                adjacent_digit_tokens = any(
                    re.fullmatch(r"\d{1,3}", row[index].strip() or "_")
                    and re.fullmatch(r"\d{3}", row[index + 1].strip() or "_")
                    for index in range(len(row) - 1)
                )
                if adjacent_digit_tokens:
                    report.possible_unquoted_thousands_separator = True

    # Numeric parseability is calculated only for rows with the expected
    # width.  Tokens remain untouched; no comma or sign normalization occurs.
    counters: dict[str, dict[str, Any]] = {
        key: {"numeric": 0, "non_missing": 0, "missing": 0, "unexpected_tokens": {}}
        for key in header_keys
    }
    dot_decimal_count = 0
    comma_decimal_count = 0
    for line_number, row in data_rows:
        if (
            line_number <= header_line
            or len(row) != report.expected_column_count
            or line_number in report.repeated_header_rows
            or line_number in report.header_continuation_rows
        ):
            continue
        for index, token in enumerate(row):
            key = header_keys[index]
            stripped = token.strip()
            is_missing, is_unexpected = _record_token(report, token, key, line_number, index)
            if is_missing:
                counters[key]["missing"] += 1
            else:
                counters[key]["non_missing"] += 1
                if not is_unexpected:
                    counters[key]["numeric"] += 1
            if _NUMBER_RE.fullmatch(stripped) and "." in stripped:
                dot_decimal_count += 1
            elif _DECIMAL_COMMA_RE.fullmatch(stripped):
                comma_decimal_count += 1
            if is_unexpected and stripped:
                unexpected = counters[key]["unexpected_tokens"]
                unexpected[stripped] = unexpected.get(stripped, 0) + 1
    for key, counter in counters.items():
        non_missing = counter["non_missing"]
        counter["numeric_percentage"] = (
            round(100.0 * counter["numeric"] / non_missing, 3) if non_missing else None
        )
        report.numeric_columns[key] = counter

    if dot_decimal_count and comma_decimal_count:
        decimal_name = "mixed"
    elif comma_decimal_count:
        decimal_name = "comma"
    elif dot_decimal_count:
        decimal_name = "dot"
    else:
        decimal_name = None
    report.decimal_convention = {
        "detected": decimal_name,
        "dot_count": dot_decimal_count,
        "comma_count": comma_decimal_count,
    }

    for index in range(len(header)):
        values = [row[index].strip() for row in all_rows_for_columns if len(row) > index]
        if values and all(not value for value in values):
            report.completely_blank_columns.append(
                {"index": index, "header": normalized_headers[index] if index < len(normalized_headers) else ""}
            )
    report.status = _status(report)
    return report


def inspect_delimited(
    path: str | Path,
    delimiter: str | None = ",",
    encoding: str | None = None,
) -> CSVInspectionReport:
    """General-name alias for :func:`inspect_csv`."""

    return inspect_csv(path, delimiter=delimiter, encoding=encoding)


__all__ = ["CSVInspectionReport", "inspect_csv", "inspect_delimited"]
