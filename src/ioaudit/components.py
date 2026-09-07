"""Diagnostics for subtotal components in final demand and value added."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .structure import _all_finite, _as_array, _shape_of, _normalize_label


_SUBTOTAL_LABELS = frozenset(
    {
        "合計",
        "計",
        "総計",
        "最終需要計",
        "最終需要合計",
        "付加価値計",
        "付加価値合計",
        "subtotal",
        "total",
        "grand total",
        "final demand total",
        "value added total",
    }
)
_NORMALIZED_SUBTOTAL_LABELS = {_normalize_label(label) for label in _SUBTOTAL_LABELS}


@dataclass
class ComponentsDiagnostics:
    """Possible subtotal components that can make ``Y`` or ``V`` double-counted."""

    status: str = "SKIPPED"
    possible_subtotal_columns: list[dict[str, Any]] = field(default_factory=list)
    possible_subtotal_rows: list[dict[str, Any]] = field(default_factory=list)
    double_count_risk: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None


def _labels(value: Any, axis: int) -> list[Any] | None:
    if isinstance(value, pd.DataFrame):
        return value.columns.tolist() if axis == 1 else value.index.tolist()
    return None


def _similarity(candidate: np.ndarray, others: np.ndarray) -> float:
    difference = float(np.linalg.norm(candidate - others))
    scale = float(np.linalg.norm(candidate))
    if scale == 0.0:
        return 1.0 if difference == 0.0 else 0.0
    return max(0.0, 1.0 - difference / scale)


def _candidates(value: Any, *, field_name: str, axis: int) -> list[dict[str, Any]]:
    """Find labelled or numerically aggregate components along one axis."""

    try:
        shape = _shape_of(value)
        array = np.asarray(_as_array(value), dtype=float)
    except (TypeError, ValueError, FloatingPointError):
        return []
    if len(shape) != 2 or not _all_finite(value):
        return []
    size = shape[axis]
    labels = _labels(value, axis)
    total = array.sum(axis=axis)
    candidates: list[dict[str, Any]] = []
    for index in range(size):
        candidate = array[index, :] if axis == 0 else array[:, index]
        others = total - candidate
        similarity = _similarity(candidate, others)
        label = labels[index] if labels is not None and index < len(labels) else None
        label_evidence = label is not None and _normalize_label(label) in _NORMALIZED_SUBTOTAL_LABELS
        # With only two components, equality to the other component is also a
        # perfectly ordinary pattern (for example, two demand categories of
        # equal size).  Numeric-only subtotal evidence is therefore enabled
        # only when there are at least three components.  A declared subtotal
        # label remains useful at any component count.
        sum_evidence = (
            size >= 3
            and similarity >= 0.999
            and bool(np.linalg.norm(candidate) > 0.0)
        )
        if not label_evidence and not sum_evidence:
            continue
        evidence_level = "strong" if label_evidence and sum_evidence else "label" if label_evidence else "numeric"
        candidates.append(
            {
                "field": field_name,
                "axis": "rows" if axis == 0 else "columns",
                "index": index,
                "label": label,
                "label_evidence": label_evidence,
                "sum_similarity": similarity,
                "evidence_level": evidence_level,
                "severity": "WARNING",
            }
        )
    return candidates


def diagnose_components(io: Any) -> ComponentsDiagnostics:
    """Inspect Y/V component dimensions without removing subtotal columns or rows."""

    result = ComponentsDiagnostics()
    available = False
    for field_name, value, axis in (("Y", getattr(io, "Y", None), 1), ("V", getattr(io, "V", None), 0)):
        if value is None:
            continue
        try:
            shape = _shape_of(value)
            if len(shape) != 2 or shape[axis] <= 1 or not _all_finite(value):
                continue
            available = True
        except Exception:
            continue
        found = _candidates(value, field_name=field_name, axis=axis)
        if axis == 1:
            result.possible_subtotal_columns.extend(found)
        else:
            result.possible_subtotal_rows.extend(found)
    result.double_count_risk = [
        {
            **candidate,
            "reason": "subtotal/total component may already include the other components",
            "double_count_risk": True,
        }
        for candidate in result.possible_subtotal_columns + result.possible_subtotal_rows
    ]
    if available:
        result.status = "AVAILABLE"
    else:
        result.reason = "Y/V has no auditable multi-component dimension"
    return result
