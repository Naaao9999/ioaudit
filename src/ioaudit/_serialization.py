"""Shared conversion helpers for serializable diagnostic reports."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
import math
from typing import Any

import numpy as np
from scipy import sparse


def jsonable(value: Any) -> Any:
    """Convert supported report values to deterministic JSON-compatible data."""

    if is_dataclass(value):
        return {
            item.name: jsonable(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [jsonable(item) for item in sorted(value, key=str)]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if sparse.issparse(value):
        matrix = value.tocoo()
        return {
            "format": "coo",
            "shape": [int(size) for size in matrix.shape],
            "row": jsonable(matrix.row),
            "column": jsonable(matrix.col),
            "data": jsonable(matrix.data),
        }
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return "Infinity" if value > 0 else ("-Infinity" if value < 0 else "NaN")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def flatten(
    value: Any,
    prefix: str,
    rows: list[dict[str, Any]],
    *,
    include_empty: bool = False,
) -> None:
    """Flatten nested report values into path/value rows."""

    if is_dataclass(value):
        for item in fields(value):
            flatten(
                getattr(value, item.name),
                f"{prefix}.{item.name}" if prefix else item.name,
                rows,
                include_empty=include_empty,
            )
    elif isinstance(value, dict):
        if not value and include_empty:
            rows.append({"path": prefix, "value": {}})
        for key, item in value.items():
            flatten(
                item,
                f"{prefix}.{key}" if prefix else str(key),
                rows,
                include_empty=include_empty,
            )
    elif isinstance(value, (list, tuple)):
        if not value and include_empty:
            rows.append({"path": prefix, "value": []})
        for index, item in enumerate(value):
            flatten(item, f"{prefix}[{index}]", rows, include_empty=include_empty)
    elif isinstance(value, np.ndarray):
        flatten(value.tolist(), prefix, rows, include_empty=include_empty)
    else:
        rows.append({"path": prefix, "value": jsonable(value)})
