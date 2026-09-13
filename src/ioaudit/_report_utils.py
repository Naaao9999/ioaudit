"""Shared implementation helpers for report serialization and path lookup."""

from __future__ import annotations

import json
from typing import Any, Iterable

import pandas as pd

from ._serialization import flatten, jsonable


MISSING = object()


def report_to_dict(report: Any, field_names: Iterable[str]) -> dict[str, Any]:
    """Serialize the selected public fields of a report."""

    return jsonable({name: getattr(report, name) for name in field_names})


def report_to_json(report: Any, field_names: Iterable[str], **kwargs: Any) -> str:
    """Serialize a report with deterministic defaults."""

    options = {"ensure_ascii": False, "indent": 2, "sort_keys": True}
    options.update(kwargs)
    return json.dumps(report_to_dict(report, field_names), **options)


def report_to_dataframe(report: Any, field_names: Iterable[str]) -> pd.DataFrame:
    """Flatten a report into ``path``/``value`` rows."""

    rows: list[dict[str, Any]] = []
    flatten(report_to_dict(report, field_names), "", rows, include_empty=True)
    return pd.DataFrame(rows, columns=["path", "value"])


def get_report_path(root: Any, path: str) -> Any:
    """Resolve a dotted attribute path without raising for missing values."""

    value = root
    for part in path.split("."):
        if not hasattr(value, part):
            return MISSING
        value = getattr(value, part)
    return value


__all__ = [
    "MISSING",
    "get_report_path",
    "report_to_dataframe",
    "report_to_dict",
    "report_to_json",
]
