"""Diagnostics for subtotal components in final demand and value added."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from .structure import (
    _all_finite,
    _as_array,
    _duplicate_normalized_labels,
    _normalize_label,
    _shape_of,
)


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


def _is_subtotal_label(label: Any) -> bool:
    """Return whether a label explicitly describes an aggregate component."""

    normalized = _normalize_label(label)
    if normalized in _NORMALIZED_SUBTOTAL_LABELS:
        return True
    # Official tables commonly qualify aggregate labels with a geography or
    # an accounting scope, for example ``都内最終需要計`` or
    # ``粗付加価値部門計``.  Keep this rule narrow so ordinary sector names
    # are not treated as subtotals merely because they contain ``計``.
    aggregate_terms = (
        "最終需要",
        "付加価値",
        "内生部門",
        "需要合計",
        "移輸出",
        "移輸入",
        "輸出",
        "輸入",
    )
    aggregate_suffixes = ("計", "合計")
    return normalized.endswith(aggregate_suffixes) and any(
        term in normalized for term in aggregate_terms
    )


@dataclass
class ComponentsDiagnostics:
    """Possible subtotal components that can make ``Y`` or ``V`` double-counted."""

    status: str = "SKIPPED"
    subtotal_candidates: list[dict[str, Any]] = field(default_factory=list)
    component_label_risks: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None

    @property
    def possible_subtotal_columns(self) -> list[dict[str, Any]]:
        """Return subtotal candidates found among component columns."""

        return [
            candidate
            for candidate in self.subtotal_candidates
            if candidate.get("axis") == "columns"
        ]

    @property
    def possible_subtotal_rows(self) -> list[dict[str, Any]]:
        """Return subtotal candidates found among component rows."""

        return [
            candidate
            for candidate in self.subtotal_candidates
            if candidate.get("axis") == "rows"
        ]

    @property
    def double_count_risk(self) -> list[dict[str, Any]]:
        """Return subtotal candidates annotated as double-count risks."""

        return [
            {
                **candidate,
                "reason": "subtotal/total component may already include the other components",
                "double_count_risk": True,
            }
            for candidate in self.subtotal_candidates
        ]


def _labels(value: Any, axis: int) -> list[Any] | None:
    if isinstance(value, pd.DataFrame):
        return value.columns.tolist() if axis == 1 else value.index.tolist()
    return None


def _similarity(candidate: np.ndarray, others: np.ndarray) -> float:
    if not np.isfinite(candidate).all() or not np.isfinite(others).all():
        return 0.0
    scale = float(max(np.max(np.abs(candidate)), np.max(np.abs(others))))
    if scale == 0.0:
        return 1.0
    with np.errstate(over="ignore", invalid="ignore"):
        difference = float(
            np.linalg.norm((candidate - others) / scale)
        )
    return max(0.0, 1.0 - difference)


def _best_subset(
    array: np.ndarray,
    *,
    axis: int,
    candidate_index: int,
    minimum_similarity: float = 0.999,
    maximum_components: int = 12,
) -> tuple[tuple[int, ...], float] | None:
    """Find a small subset whose component sum matches one candidate.

    Subset search is intentionally bounded.  It is useful for the small
    component panels found in published IO tables, but exhaustive search is
    not an appropriate operation for a large satellite account matrix.
    """

    size = array.shape[axis]
    if size < 3 or size > maximum_components:
        return None
    candidate = array[candidate_index, :] if axis == 0 else array[:, candidate_index]
    if not np.any(candidate != 0):
        return None
    nonzero = np.any(array != 0, axis=1 - axis)
    other_indices = [
        index for index in range(size)
        if index != candidate_index and nonzero[index]
    ]
    best: tuple[tuple[int, ...], float] | None = None
    for subset_size in range(2, len(other_indices) + 1):
        for subset in combinations(other_indices, subset_size):
            with np.errstate(over="ignore", invalid="ignore"):
                if axis == 0:
                    aggregate = array[list(subset), :].sum(axis=0)
                else:
                    aggregate = array[:, list(subset)].sum(axis=1)
            similarity = _similarity(candidate, aggregate)
            if similarity < minimum_similarity:
                continue
            if best is None or similarity > best[1] or (
                similarity == best[1] and len(subset) < len(best[0])
            ):
                best = (tuple(subset), similarity)
    return best


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
    nonzero = np.any(array != 0, axis=1 - axis)
    labels = _labels(value, axis)
    with np.errstate(over="ignore", invalid="ignore"):
        total = array.sum(axis=axis)
    candidates: list[dict[str, Any]] = []
    for index in range(size):
        candidate = array[index, :] if axis == 0 else array[:, index]
        others = total - candidate
        similarity = _similarity(candidate, others)
        label = labels[index] if labels is not None and index < len(labels) else None
        label_evidence = label is not None and _is_subtotal_label(label)
        # With only two components, equality to the other component is also a
        # perfectly ordinary pattern (for example, two demand categories of
        # equal size).  Numeric-only subtotal evidence is therefore enabled
        # only when there are at least three components.  A declared subtotal
        # label remains useful at any component count.
        sum_evidence = (
            np.count_nonzero(nonzero) - int(nonzero[index]) >= 2
            and similarity >= 0.999
            and bool(np.any(candidate != 0))
        )
        subset_match = _best_subset(
            array,
            axis=axis,
            candidate_index=index,
        )
        subset_evidence = subset_match is not None
        if not label_evidence and not sum_evidence and not subset_evidence:
            continue
        if subset_match is not None:
            subset_indices, subset_similarity = subset_match
            selected_similarity = subset_similarity
        else:
            subset_indices = tuple()
            selected_similarity = similarity
        if label_evidence and (sum_evidence or subset_evidence):
            evidence_level = "strong"
        elif label_evidence:
            evidence_level = "label"
        else:
            evidence_level = "numeric"
        item: dict[str, Any] = {
            "field": field_name,
            "axis": "rows" if axis == 0 else "columns",
            "index": index,
            "label": label,
            "label_evidence": label_evidence,
            "sum_similarity": selected_similarity,
            "evidence_level": evidence_level,
            "severity": "WARNING",
        }
        if subset_match is not None:
            item.update(
                {
                    "aggregation_type": (
                        "all_other_sum"
                        if len(subset_indices) == size - 1
                        else "subset_sum"
                    ),
                    "subset_indices": list(subset_indices),
                    "subset_labels": [
                        labels[subset_index]
                        if labels is not None and subset_index < len(labels)
                        else None
                        for subset_index in subset_indices
                    ],
                    "subset_size": len(subset_indices),
                }
            )
        candidates.append(item)
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
        result.subtotal_candidates.extend(found)
        if axis == 1:
            if isinstance(value, pd.DataFrame):
                result.component_label_risks.extend(
                    {
                        **duplicate,
                        "field": field_name,
                        "reason": "component labels are duplicated after Unicode/whitespace normalization",
                    }
                    for duplicate in _duplicate_normalized_labels(
                        value.columns.tolist(), f"{field_name}.columns"
                    )
                )
        else:
            if isinstance(value, pd.DataFrame):
                result.component_label_risks.extend(
                    {
                        **duplicate,
                        "field": field_name,
                        "reason": "component labels are duplicated after Unicode/whitespace normalization",
                    }
                    for duplicate in _duplicate_normalized_labels(
                        value.index.tolist(), f"{field_name}.index"
                    )
                )
    if available:
        result.status = (
            "WARNING"
            if result.double_count_risk or result.component_label_risks
            else "AVAILABLE"
        )
    else:
        result.reason = "Y/V has no auditable multi-component dimension"
    return result
