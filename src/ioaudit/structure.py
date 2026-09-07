"""Structural diagnostics and safe conversion helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import numbers
import re
from typing import Any
import unicodedata

import numpy as np
import pandas as pd

from .model import IOSystem, _TRADE_FLOW_FIELDS


PASS = "PASS"
FAIL = "FAIL"
SKIPPED = "SKIPPED"
WARNING = "WARNING"


def _as_array(value: Any) -> np.ndarray:
    """Return a non-mutating dense view for diagnostic calculations."""

    try:
        from scipy import sparse

        if sparse.issparse(value):
            return value.toarray()
    except Exception:
        pass
    if isinstance(value, pd.DataFrame):
        return value.to_numpy(copy=True)
    if isinstance(value, pd.Series):
        return value.to_numpy(copy=True)
    return np.array(value, copy=True)


def _is_sparse(value: Any) -> bool:
    """Return whether ``value`` is a SciPy sparse matrix."""

    try:
        from scipy import sparse

        return bool(sparse.issparse(value))
    except Exception:
        return False


def _shape_of(value: Any) -> tuple[int, ...]:
    """Read a shape without densifying sparse matrices."""

    if _is_sparse(value):
        return tuple(int(size) for size in value.shape)
    return tuple(int(size) for size in _as_array(value).shape)


def _nonfinite_flags(value: Any) -> tuple[bool, bool]:
    """Return NaN and Inf flags without densifying sparse matrices."""

    if _is_sparse(value):
        data = np.asarray(value.data)
        if data.size == 0:
            return False, False
        return bool(np.isnan(data).any()), bool(np.isinf(data).any())
    array = _as_array(value)
    if array.dtype.kind not in "biufc":
        return False, False
    return bool(np.isnan(array).any()), bool(np.isinf(array).any())


def _all_finite(value: Any) -> bool:
    """Return finiteness for dense and sparse numeric values."""

    nan_exists, inf_exists = _nonfinite_flags(value)
    return not nan_exists and not inf_exists


def _labels(value: Any) -> tuple[list[Any] | None, list[Any] | None]:
    if isinstance(value, pd.DataFrame):
        return value.index.tolist(), value.columns.tolist()
    if isinstance(value, pd.Series):
        return value.index.tolist(), None
    return None, None


def _is_missing(value: Any) -> bool:
    try:
        result = pd.isna(value)
        return bool(result) if np.ndim(result) == 0 else False
    except Exception:
        return False


def _numeric_array(value: Any) -> tuple[Any | None, list[tuple[int, ...]]]:
    """Convert real numeric data and return locations of non-numeric values."""

    if _is_sparse(value):
        try:
            from scipy import sparse

            sparse_value = value.copy()
            data = np.asarray(sparse_value.data)
            if data.dtype.kind in "iuf":
                return sparse_value.astype(float), []
            locations: list[tuple[int, ...]] = []
            coo = sparse_value.tocoo()
            for row, column, item in zip(coo.row, coo.col, data):
                if _is_missing(item) or not isinstance(item, numbers.Real) or isinstance(item, bool):
                    locations.append((int(row), int(column)))
            if locations:
                return None, locations
            return sparse_value.astype(float), []
        except Exception:
            return None, [()]
    try:
        array = _as_array(value)
    except Exception:
        return None, [()]
    locations: list[tuple[int, ...]] = []
    if array.dtype.kind in "iuf":
        return array.astype(float, copy=False), locations
    if array.dtype.kind == "c":
        locations = [tuple(index) for index in np.ndindex(array.shape)]
        return None, locations
    for index in np.ndindex(array.shape):
        item = array[index]
        if _is_missing(item) or not isinstance(item, numbers.Real) or isinstance(item, bool):
            locations.append(tuple(int(i) for i in index))
    if locations:
        return None, locations
    try:
        return array.astype(float), []
    except (TypeError, ValueError):
        return None, [()]


def _same_labels(left: list[Any] | None, right: list[Any] | None) -> bool | None:
    if left is None or right is None:
        return None
    if len(left) != len(right):
        return False
    return all(a == b for a, b in zip(left, right))


def _normalize_label(value: Any) -> str:
    """Normalize Unicode width, whitespace, and case for label diagnostics."""

    normalized = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def _normalized_labels(labels: list[Any] | None) -> list[str] | None:
    if labels is None:
        return None
    return [_normalize_label(label) for label in labels]


def _same_normalized_labels(
    left: list[Any] | None, right: list[Any] | None
) -> bool | None:
    normalized_left = _normalized_labels(left)
    normalized_right = _normalized_labels(right)
    return _same_labels(normalized_left, normalized_right)


def _alignment_is_safe(exact: bool | None, normalized: bool | None) -> bool:
    """Return whether positional use is safe under the label policy.

    Unlabelled arrays are positional by definition.  A normalized-only match
    is also safe because normalization preserves the declared order.  A
    genuine mismatch is unsafe and must prevent dependent calculations from
    consuming the values positionally.
    """

    return exact is not False or normalized is True


def _core_inputs_are_safe(result: Any) -> bool:
    """Return whether Z, x, and the sector axis are safe for derived math."""

    required = (
        result.z_is_2d == PASS,
        result.z_is_square == PASS,
        result.x_length_matches == PASS,
        result.sectors_length_matches == PASS,
        result.non_numeric is not True
        or not ({"Z", "x"} & set(result.details.get("non_numeric_fields", []))),
        not ({"Z", "x"} & set(result.details.get("nan_fields", []))),
        not ({"Z", "x"} & set(result.details.get("inf_fields", []))),
        result.duplicate_sector_ids is not True,
        not bool(result.details.get("core_normalized_duplicates")),
        _alignment_is_safe(
            result.row_column_labels_match,
            result.normalized_row_column_labels_match,
        ),
        _alignment_is_safe(
            result.z_row_labels_match_sectors,
            result.normalized_z_row_labels_match_sectors,
        ),
        _alignment_is_safe(
            result.z_column_labels_match_sectors,
            result.normalized_z_column_labels_match_sectors,
        ),
        _alignment_is_safe(result.x_labels_match, result.normalized_x_labels_match),
    )
    return all(required)


def _duplicate_normalized_labels(
    labels: list[Any] | None, dimension: str
) -> list[dict[str, Any]]:
    if labels is None:
        return []
    groups: dict[str, list[int]] = {}
    for index, label in enumerate(labels):
        groups.setdefault(_normalize_label(label), []).append(index)
    duplicates: list[dict[str, Any]] = []
    for normalized, indices in groups.items():
        if len(indices) > 1:
            duplicates.append(
                {
                    "dimension": dimension,
                    "normalized_label": normalized,
                    "indices": indices,
                    "labels": [labels[index] for index in indices],
                    "severity": "WARNING",
                }
            )
    return duplicates


_NONSECTOR_LABELS = frozenset(
    {
        "合計",
        "計",
        "総計",
        "total",
        "grand total",
        "subtotal",
        "最終需要",
        "家計消費",
        "家計消費支出",
        "政府消費",
        "固定資本形成",
        "投資",
        "在庫",
        "輸出",
        "輸入",
        "移出",
        "移入",
        "移輸出",
        "移輸入",
        "粗付加価値",
        "付加価値",
        "雇用者所得",
        "営業余剰",
        "税",
        "間接税",
        "補助金",
        "労働報酬",
    }
)


def _possible_nonsector_labels(
    labels: list[Any] | None, *, axis: str
) -> list[dict[str, Any]]:
    if labels is None:
        return []
    candidates: list[dict[str, Any]] = []
    known_labels = {_normalize_label(item) for item in _NONSECTOR_LABELS}
    for index, label in enumerate(labels):
        normalized = _normalize_label(label)
        if normalized in known_labels:
            candidates.append(
                {
                    "axis": axis,
                    "index": index,
                    "label": label,
                    "normalized_label": normalized,
                    "label_evidence": True,
                    "severity": "WARNING",
                }
            )
    return candidates


def _duplicate_lines(
    value: Any,
    axis: int,
    labels: list[Any] | None,
) -> list[dict[str, Any]]:
    """Find exact duplicate rows or columns, without modifying ``value``."""

    try:
        shape = _shape_of(value)
        numeric_value, bad = _numeric_array(value)
        if len(shape) != 2 or bad or numeric_value is None or not _all_finite(numeric_value):
            return []
        size = shape[0] if axis == 0 else shape[1]
    except (TypeError, ValueError, FloatingPointError):
        return []
    duplicates: list[dict[str, Any]] = []
    if _is_sparse(value):
        lines = [numeric_value.getrow(index) if axis == 0 else numeric_value.getcol(index) for index in range(size)]
        equal = lambda first, second: (lines[first] != lines[second]).nnz == 0
    else:
        vectors = [_dimension_vector(numeric_value, axis, index) for index in range(size)]
        equal = lambda first, second: np.array_equal(vectors[first], vectors[second])
    for first in range(size):
        for second in range(first + 1, size):
            if equal(first, second):
                duplicates.append(
                    {
                        "first_index": first,
                        "second_index": second,
                        "first_label": labels[first] if labels and first < len(labels) else None,
                        "second_label": labels[second] if labels and second < len(labels) else None,
                        "severity": "WARNING",
                    }
                )
    return duplicates


@dataclass
class StructureDiagnostics:
    status: str = SKIPPED
    z_is_2d: str = SKIPPED
    z_is_square: str = SKIPPED
    x_length_matches: str = SKIPPED
    sectors_length_matches: str = SKIPPED
    duplicate_sector_ids: bool | None = None
    nan_exists: bool | None = None
    inf_exists: bool | None = None
    non_numeric: bool | None = None
    non_numeric_locations: list[tuple[int, ...]] = field(default_factory=list)
    row_column_labels_match: bool | None = None
    normalized_row_column_labels_match: bool | None = None
    exact_labels_match: bool | None = None
    normalized_labels_match: bool | None = None
    z_row_labels_match_sectors: bool | None = None
    normalized_z_row_labels_match_sectors: bool | None = None
    z_column_labels_match_sectors: bool | None = None
    normalized_z_column_labels_match_sectors: bool | None = None
    x_labels_match: bool | None = None
    normalized_x_labels_match: bool | None = None
    y_labels_match: bool | None = None
    normalized_y_labels_match: bool | None = None
    v_labels_match: bool | None = None
    normalized_v_labels_match: bool | None = None
    input_adjustment_labels_match: bool | None = None
    normalized_input_adjustment_labels_match: bool | None = None
    trade_labels_match: dict[str, bool | None] = field(default_factory=dict)
    normalized_trade_labels_match: dict[str, bool | None] = field(default_factory=dict)
    y_shape: str = SKIPPED
    v_shape: str = SKIPPED
    possible_total_rows: list[dict[str, Any]] = field(default_factory=list)
    possible_total_columns: list[dict[str, Any]] = field(default_factory=list)
    possible_total_vector: list[dict[str, Any]] = field(default_factory=list)
    possible_nonsector_rows: list[dict[str, Any]] = field(default_factory=list)
    possible_nonsector_columns: list[dict[str, Any]] = field(default_factory=list)
    possible_duplicate_rows: list[dict[str, Any]] = field(default_factory=list)
    possible_duplicate_columns: list[dict[str, Any]] = field(default_factory=list)
    duplicate_labels_after_normalization: list[dict[str, Any]] = field(default_factory=list)
    trade_representation_conflicts: list[str] = field(default_factory=list)
    trade_shape: dict[str, str] = field(default_factory=dict)
    supporting_status: str = SKIPPED
    supporting_failures: list[str] = field(default_factory=list)
    supporting_warnings: list[str] = field(default_factory=list)
    n_rows: int | None = None
    n_columns: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _shape_status(value: Any, expected: tuple[int, ...] | None) -> str:
    if value is None:
        return SKIPPED
    try:
        shape = _shape_of(value)
    except Exception:
        return FAIL
    if expected is None:
        return PASS
    return PASS if shape in expected else FAIL


_TOTAL_LABELS = frozenset({"合計", "計", "総計", "total", "grand total", "subtotal"})


def _normalized_total_label(value: Any) -> bool:
    if value is None:
        return False
    normalized = _normalize_label(value)
    return normalized in {_normalize_label(label) for label in _TOTAL_LABELS}


def _dimension_labels(io: IOSystem, axis: int, size: int) -> list[Any] | None:
    if isinstance(io.Z, pd.DataFrame):
        labels = io.Z.index.tolist() if axis == 0 else io.Z.columns.tolist()
        return labels if len(labels) == size else labels
    if len(io.sectors) == size:
        return list(io.sectors)
    return None


def _dimension_vector(value: Any, axis: int, index: int) -> np.ndarray:
    if _is_sparse(value):
        from scipy import sparse

        matrix = value.getrow(index) if axis == 0 else value.getcol(index)
        return np.asarray(matrix.toarray(), dtype=float).reshape(-1)
    array = np.asarray(value, dtype=float)
    return array[index, :] if axis == 0 else array[:, index]


def _sum_similarity(
    value: Any,
    axis: int,
    index: int,
    total: np.ndarray | None = None,
) -> float | None:
    """Compare one row/column with the sum of all other rows/columns."""

    try:
        candidate = _dimension_vector(value, axis, index)
        if total is None:
            total = _axis_sum_for_total(value, axis)
        others = total - candidate
        scale = float(
            max(
                np.max(np.abs(candidate)) if candidate.size else 0.0,
                np.max(np.abs(others)) if others.size else 0.0,
            )
        )
        if scale == 0.0:
            return 1.0
        candidate_scaled = candidate / scale
        others_scaled = others / scale
        denominator = float(np.linalg.norm(candidate_scaled))
        difference = float(np.linalg.norm(candidate_scaled - others_scaled))
        if denominator == 0.0:
            return 1.0 if difference == 0.0 else 0.0
        return max(0.0, 1.0 - difference / denominator)
    except (TypeError, ValueError, FloatingPointError):
        return None


def _axis_sum_for_total(value: Any, axis: int) -> np.ndarray:
    summed = value.sum(axis=axis) if hasattr(value, "sum") else np.asarray(value, dtype=float).sum(axis=axis)
    return np.asarray(summed, dtype=float).reshape(-1)


def _total_candidates(value: Any, labels: list[Any] | None, axis: int) -> list[dict[str, Any]]:
    shape = _shape_of(value)
    size = shape[0] if axis == 0 else shape[1]
    candidates: list[dict[str, Any]] = []
    total: np.ndarray | None = None
    if _all_finite(value):
        try:
            # Compute the aggregate once. Recomputing it for every candidate
            # makes total-row/column screening unnecessarily expensive.
            total = _axis_sum_for_total(value, axis)
        except (TypeError, ValueError, FloatingPointError):
            total = None
    for index in range(size):
        label = labels[index] if labels is not None and index < len(labels) else None
        label_evidence = _normalized_total_label(label)
        similarity = _sum_similarity(value, axis, index, total) if total is not None else None
        try:
            nonzero_candidate = bool(
                np.any(_dimension_vector(value, axis, index) != 0)
            )
        except (TypeError, ValueError, FloatingPointError):
            nonzero_candidate = False
        sum_evidence = similarity is not None and similarity >= 0.999 and nonzero_candidate
        if not label_evidence and not sum_evidence:
            continue
        if label_evidence and sum_evidence:
            evidence_level = "certain" if shape[0] != shape[1] else "likely"
        elif label_evidence:
            evidence_level = "possible"
        else:
            evidence_level = "possible"
        candidates.append(
            {
                "index": index,
                "label": label,
                "label_evidence": label_evidence,
                "sum_similarity": similarity,
                "evidence_level": evidence_level,
                "severity": "WARNING",
            }
        )
    return candidates


def _possible_total_vector(io: IOSystem, z_shape: tuple[int, ...]) -> list[dict[str, Any]]:
    if len(z_shape) < 2:
        return []
    try:
        x_shape = _shape_of(io.x)
        x_length = x_shape[0] if len(x_shape) == 1 else None
    except Exception:
        return []
    candidates: list[dict[str, Any]] = []
    x_index, _ = _labels(io.x)
    if x_length is not None and x_length not in {z_shape[0], z_shape[1]}:
        candidates.append(
            {
                "reason": "x length differs from both Z dimensions",
                "x_length": x_length,
                "z_rows": z_shape[0],
                "z_columns": z_shape[1],
                "severity": "WARNING",
            }
        )
    if x_index is not None:
        for index, label in enumerate(x_index):
            if _normalized_total_label(label):
                candidates.append(
                    {
                        "index": index,
                        "label": label,
                        "label_evidence": True,
                        "evidence_level": "possible",
                        "severity": "WARNING",
                    }
                )
    x_name = getattr(io.x, "name", None)
    if _normalized_total_label(x_name):
        candidates.append(
            {
                "index": None,
                "label": x_name,
                "label_evidence": True,
                "evidence_level": "possible",
                "severity": "WARNING",
            }
        )
    return candidates


def diagnose_structure(io: IOSystem) -> tuple[StructureDiagnostics, dict[str, Any]]:
    """Inspect shapes, labels, numeric content, and return safe arrays."""

    result = StructureDiagnostics()
    arrays: dict[str, Any] = {}
    try:
        z_shape = _shape_of(io.Z)
    except Exception as exc:
        result.status = FAIL
        result.z_is_2d = FAIL
        result.details["error"] = str(exc)
        return result, arrays

    result.n_rows = int(z_shape[0]) if len(z_shape) >= 1 else None
    result.n_columns = int(z_shape[1]) if len(z_shape) >= 2 else None
    result.z_is_2d = PASS if len(z_shape) == 2 else FAIL
    result.z_is_square = (
        PASS if len(z_shape) == 2 and z_shape[0] == z_shape[1] else FAIL
    )
    if len(z_shape) == 2 and z_shape[0] != z_shape[1]:
        result.details["possible_extra_row_or_column"] = {
            "rows": int(z_shape[0]),
            "columns": int(z_shape[1]),
        }

    z_numeric, bad = _numeric_array(io.Z)
    non_numeric_fields: list[str] = ["Z"] if bad else []
    supporting_non_numeric_fields: list[str] = []
    result.non_numeric = bool(bad)
    result.non_numeric_locations = bad
    finite_fields_seen = False
    nan_fields: list[str] = []
    inf_fields: list[str] = []
    supporting_nan_fields: list[str] = []
    supporting_inf_fields: list[str] = []
    if z_numeric is not None and len(z_numeric.shape) == 2:
        arrays["Z"] = z_numeric
        finite_fields_seen = True
        z_nan, z_inf = _nonfinite_flags(z_numeric)
        if z_nan:
            nan_fields.append("Z")
        if z_inf:
            inf_fields.append("Z")
    else:
        result.nan_exists = None
        result.inf_exists = None

    x_numeric, x_bad = _numeric_array(io.x)
    if x_numeric is not None and x_numeric.ndim == 1:
        arrays["x"] = x_numeric
        if result.n_rows is not None:
            result.x_length_matches = PASS if len(x_numeric) == result.n_rows else FAIL
        else:
            result.x_length_matches = FAIL
    else:
        result.x_length_matches = FAIL
        if x_bad:
            non_numeric_fields.append("x")
            result.details["x_non_numeric_locations"] = x_bad
    if x_numeric is not None:
        finite_fields_seen = True
        x_nan, x_inf = _nonfinite_flags(x_numeric)
        if x_nan:
            nan_fields.append("x")
        if x_inf:
            inf_fields.append("x")

    # Inspect table components that participate in accounting.  References
    # are optional validation targets and are diagnosed by ``reference.py``.
    for field_name in ("Y", "V"):
        value = getattr(io, field_name)
        if value is None:
            continue
        field_array, field_bad = _numeric_array(value)
        if field_bad:
            non_numeric_fields.append(field_name)
            result.details[f"{field_name}_non_numeric_locations"] = field_bad
            continue
        if field_array is not None:
            finite_fields_seen = True
            field_nan, field_inf = _nonfinite_flags(field_array)
            if field_nan:
                nan_fields.append(field_name)
            if field_inf:
                inf_fields.append(field_name)
    trade = getattr(io, "trade", None)
    if trade is not None:
        result.trade_representation_conflicts = list(trade.representation_conflicts)
        for field_name in _TRADE_FLOW_FIELDS:
            value = getattr(trade, field_name)
            if value is None:
                continue
            field_array, field_bad = _numeric_array(value)
            qualified_name = f"trade.{field_name}"
            if field_bad:
                supporting_non_numeric_fields.append(qualified_name)
                result.details[f"{qualified_name}_non_numeric_locations"] = field_bad
                continue
            if field_array is not None:
                if result.n_rows is not None:
                    result.trade_shape[qualified_name] = (
                        PASS if _shape_of(field_array) == (result.n_rows,) else FAIL
                    )
                field_index, field_columns = _labels(value)
                flow_labels = field_index if field_columns is None else field_index
                if flow_labels is not None and len(io.sectors) == result.n_rows:
                    result.trade_labels_match[qualified_name] = _same_labels(
                        flow_labels, list(io.sectors)
                    )
                    result.normalized_trade_labels_match[qualified_name] = _same_normalized_labels(
                        flow_labels, list(io.sectors)
                    )
                field_nan, field_inf = _nonfinite_flags(field_array)
                if field_nan:
                    supporting_nan_fields.append(qualified_name)
                if field_inf:
                    supporting_inf_fields.append(qualified_name)
    result.non_numeric = bool(non_numeric_fields)
    result.details["non_numeric_fields"] = non_numeric_fields
    result.details["supporting_non_numeric_fields"] = supporting_non_numeric_fields
    result.nan_exists = bool(nan_fields) if finite_fields_seen else None
    result.inf_exists = bool(inf_fields) if finite_fields_seen else None
    if nan_fields:
        result.details["nan_fields"] = nan_fields
    if inf_fields:
        result.details["inf_fields"] = inf_fields
    if supporting_nan_fields:
        result.details["supporting_nan_fields"] = supporting_nan_fields
    if supporting_inf_fields:
        result.details["supporting_inf_fields"] = supporting_inf_fields
    result.sectors_length_matches = (
        PASS if result.n_rows is not None and len(io.sectors) == result.n_rows else FAIL
    )
    try:
        result.duplicate_sector_ids = bool(pd.Index(io.sectors).has_duplicates)
    except Exception:
        result.duplicate_sector_ids = True

    expected_sector_labels = list(io.sectors) if result.n_rows == len(io.sectors) else None
    z_index, z_columns = _labels(io.Z)
    result.row_column_labels_match = _same_labels(z_index, z_columns)
    result.normalized_row_column_labels_match = _same_normalized_labels(z_index, z_columns)
    result.z_row_labels_match_sectors = (
        _same_labels(z_index, expected_sector_labels)
        if z_index is not None and expected_sector_labels is not None
        else None
    )
    result.normalized_z_row_labels_match_sectors = (
        _same_normalized_labels(z_index, expected_sector_labels)
        if z_index is not None and expected_sector_labels is not None
        else None
    )
    result.z_column_labels_match_sectors = (
        _same_labels(z_columns, expected_sector_labels)
        if z_columns is not None and expected_sector_labels is not None
        else None
    )
    result.normalized_z_column_labels_match_sectors = (
        _same_normalized_labels(z_columns, expected_sector_labels)
        if z_columns is not None and expected_sector_labels is not None
        else None
    )
    x_index, _ = _labels(io.x)
    result.x_labels_match = _same_labels(x_index, list(io.sectors)) if x_index is not None else None
    result.normalized_x_labels_match = (
        _same_normalized_labels(x_index, list(io.sectors)) if x_index is not None else None
    )
    y_index, y_columns = _labels(io.Y)
    result.y_labels_match = (
        _same_labels(y_index, expected_sector_labels)
        if y_index is not None and expected_sector_labels is not None
        else None
    )
    result.normalized_y_labels_match = (
        _same_normalized_labels(y_index, expected_sector_labels)
        if y_index is not None and expected_sector_labels is not None
        else None
    )
    v_index, v_columns = _labels(io.V)
    if v_columns is not None:
        result.v_labels_match = (
            _same_labels(v_columns, expected_sector_labels)
            if expected_sector_labels is not None
            else None
        )
    elif v_index is not None:
        result.v_labels_match = (
            _same_labels(v_index, expected_sector_labels)
            if expected_sector_labels is not None
            else None
        )
    else:
        result.v_labels_match = None
    v_sector_labels = v_columns if v_columns is not None else v_index
    result.normalized_v_labels_match = (
        _same_normalized_labels(v_sector_labels, expected_sector_labels)
        if v_sector_labels is not None and expected_sector_labels is not None
        else None
    )
    value = getattr(io, "input_adjustments", None)
    if value is not None and expected_sector_labels is not None:
        field_index, field_columns = _labels(value)
        # For an (m, n) adjustment matrix, columns identify purchasing
        # sectors.  For a one-dimensional Series, its index does so.
        sector_labels = field_columns if field_columns is not None else field_index
        result.input_adjustment_labels_match = _same_labels(
            sector_labels, expected_sector_labels
        )
        result.normalized_input_adjustment_labels_match = _same_normalized_labels(
            sector_labels, expected_sector_labels
        )
    exact_label_checks = [
        value
        for value in (
            result.row_column_labels_match,
            result.z_row_labels_match_sectors,
            result.z_column_labels_match_sectors,
            result.x_labels_match,
            result.y_labels_match,
            result.v_labels_match,
        )
        if value is not None
    ]
    normalized_label_checks = [
        value
        for value in (
            result.normalized_row_column_labels_match,
            result.normalized_z_row_labels_match_sectors,
            result.normalized_z_column_labels_match_sectors,
            result.normalized_x_labels_match,
            result.normalized_y_labels_match,
            result.normalized_v_labels_match,
        )
        if value is not None
    ]
    result.exact_labels_match = (
        all(exact_label_checks) if exact_label_checks else None
    )
    result.normalized_labels_match = (
        all(normalized_label_checks) if normalized_label_checks else None
    )
    result.duplicate_labels_after_normalization.extend(
        _duplicate_normalized_labels(z_index, "Z.index")
    )
    result.duplicate_labels_after_normalization.extend(
        _duplicate_normalized_labels(z_columns, "Z.columns")
    )
    result.duplicate_labels_after_normalization.extend(
        _duplicate_normalized_labels(list(io.sectors), "sectors")
    )
    result.duplicate_labels_after_normalization.extend(
        _duplicate_normalized_labels(x_index, "x.index")
    )
    result.duplicate_labels_after_normalization.extend(
        _duplicate_normalized_labels(y_index, "Y.index")
    )
    result.duplicate_labels_after_normalization.extend(
        _duplicate_normalized_labels(y_columns, "Y.columns")
    )
    result.duplicate_labels_after_normalization.extend(
        _duplicate_normalized_labels(v_index, "V.index")
    )
    result.duplicate_labels_after_normalization.extend(
        _duplicate_normalized_labels(v_columns, "V.columns")
    )
    value = getattr(io, "input_adjustments", None)
    field_index, field_columns = _labels(value)
    if field_columns is not None:
        result.duplicate_labels_after_normalization.extend(
            _duplicate_normalized_labels(field_columns, "input_adjustments.columns")
        )
    elif field_index is not None:
        result.duplicate_labels_after_normalization.extend(
            _duplicate_normalized_labels(field_index, "input_adjustments.index")
        )

    core_dimensions = {
        "Z.index",
        "Z.columns",
        "sectors",
        "x.index",
    }
    accounting_dimensions = {
        "Y.index",
        "V.columns",
    }
    component_dimensions = {
        "Y.columns",
        "V.index",
    }
    supporting_dimensions = {
        "input_adjustments.columns",
        "input_adjustments.index",
    }
    core_normalized_duplicates = [
        duplicate
        for duplicate in result.duplicate_labels_after_normalization
        if duplicate.get("dimension") in core_dimensions
    ]
    accounting_normalized_duplicates = [
        duplicate
        for duplicate in result.duplicate_labels_after_normalization
        if duplicate.get("dimension") in accounting_dimensions
    ]
    component_normalized_duplicates = [
        duplicate
        for duplicate in result.duplicate_labels_after_normalization
        if duplicate.get("dimension") in component_dimensions
    ]
    supporting_normalized_duplicates = [
        duplicate
        for duplicate in result.duplicate_labels_after_normalization
        if duplicate.get("dimension") in supporting_dimensions
        or str(duplicate.get("dimension", "")).startswith("trade.")
    ]
    result.details["core_normalized_duplicates"] = core_normalized_duplicates
    result.details["accounting_normalized_duplicates"] = accounting_normalized_duplicates
    result.details["component_normalized_duplicates"] = component_normalized_duplicates
    result.details["supporting_normalized_duplicates"] = supporting_normalized_duplicates

    normalized_label_warnings: list[str] = []
    for name, exact, normalized in (
        ("Z row labels / sectors", result.z_row_labels_match_sectors, result.normalized_z_row_labels_match_sectors),
        ("Z column labels / sectors", result.z_column_labels_match_sectors, result.normalized_z_column_labels_match_sectors),
        ("Z row / column labels", result.row_column_labels_match, result.normalized_row_column_labels_match),
        ("x labels / sectors", result.x_labels_match, result.normalized_x_labels_match),
        ("Y labels / sectors", result.y_labels_match, result.normalized_y_labels_match),
        ("V labels / sectors", result.v_labels_match, result.normalized_v_labels_match),
    ):
        if exact is False and normalized is True:
            normalized_label_warnings.append(
                f"{name} match only after Unicode/whitespace normalization"
            )
    result.details["normalized_label_warnings"] = normalized_label_warnings

    # Trade flows and input adjustments support accounting checks but are not
    # part of the core Z/x/Y/V table.  Keep their failures local so a bad
    # supporting vector does not prevent coefficients or stability from being
    # audited for an otherwise valid core table.
    supporting_present = value is not None or (
        trade is not None and trade.has_any
    )
    supporting_failures: list[str] = []
    supporting_warnings: list[str] = []
    if value is not None:
        adjustment_array, adjustment_bad = _numeric_array(value)
        if adjustment_bad or adjustment_array is None:
            supporting_failures.append("input_adjustments contains non-numeric values")
        elif result.n_rows is not None:
            adjustment_shape = _shape_of(adjustment_array)
            if adjustment_shape not in {
                (result.n_rows,),
                (result.n_rows, result.n_rows),
            } and not (
                len(adjustment_shape) == 2 and adjustment_shape[1] == result.n_rows
            ):
                supporting_failures.append(
                    "input_adjustments must have shape (n,) or (m, n)"
                )
            if not _all_finite(adjustment_array):
                supporting_failures.append("input_adjustments contains NaN/Inf")
        if (
            result.input_adjustment_labels_match is False
            and result.normalized_input_adjustment_labels_match is True
        ):
            supporting_warnings.append(
                "input_adjustments labels match sectors only after Unicode/whitespace normalization"
            )
        elif (
            result.input_adjustment_labels_match is False
            and result.normalized_input_adjustment_labels_match is not True
        ):
            supporting_failures.append("input_adjustments labels do not match sectors")

    for qualified_name, exact in result.trade_labels_match.items():
        normalized = result.normalized_trade_labels_match.get(qualified_name)
        if exact is False and normalized is True:
            supporting_warnings.append(
                f"{qualified_name} labels match sectors only after Unicode/whitespace normalization"
            )
        elif exact is False and normalized is not True:
            supporting_failures.append(f"{qualified_name} labels do not match sectors")
    supporting_failures.extend(
        f"{name} has invalid shape" for name, status in result.trade_shape.items() if status == FAIL
    )
    if result.trade_representation_conflicts:
        supporting_failures.append(
            "combined and split trade representations were supplied together"
        )
    supporting_failures.extend(
        f"{name} contains non-numeric values" for name in supporting_non_numeric_fields
    )
    supporting_failures.extend(
        f"{name} contains NaN/Inf" for name in supporting_nan_fields + supporting_inf_fields
    )
    if supporting_normalized_duplicates:
        supporting_failures.append(
            "supporting labels are duplicated after Unicode/whitespace normalization"
        )
    result.supporting_failures = sorted(set(supporting_failures))
    result.supporting_warnings = sorted(set(supporting_warnings))
    if result.supporting_failures:
        result.supporting_status = FAIL
    elif result.supporting_warnings:
        result.supporting_status = WARNING
    elif supporting_present:
        result.supporting_status = PASS
    else:
        result.supporting_status = SKIPPED
    result.details["supporting_failures"] = result.supporting_failures
    result.details["supporting_warnings"] = result.supporting_warnings
    if len(z_shape) == 2:
        result.possible_total_rows = _total_candidates(
            io.Z, _dimension_labels(io, 0, z_shape[0]), axis=0
        )
        result.possible_total_columns = _total_candidates(
            io.Z, _dimension_labels(io, 1, z_shape[1]), axis=1
        )
        result.possible_total_vector = _possible_total_vector(io, z_shape)
        row_labels = _dimension_labels(io, 0, z_shape[0])
        column_labels = _dimension_labels(io, 1, z_shape[1])
        result.possible_nonsector_rows = _possible_nonsector_labels(
            row_labels, axis="rows"
        )
        result.possible_nonsector_columns = _possible_nonsector_labels(
            column_labels, axis="columns"
        )
        result.possible_duplicate_rows = _duplicate_lines(io.Z, 0, row_labels)
        result.possible_duplicate_columns = _duplicate_lines(io.Z, 1, column_labels)

    n = result.n_rows if result.z_is_square == PASS else None
    if n is not None:
        result.y_shape = _shape_status(io.Y, ((n,),))
        if io.Y is not None:
            try:
                y_shape = _shape_of(io.Y)
                result.y_shape = PASS if y_shape == (n,) or (len(y_shape) == 2 and y_shape[0] == n) else FAIL
            except Exception:
                result.y_shape = FAIL
        result.v_shape = SKIPPED if io.V is None else FAIL
        if io.V is not None:
            try:
                v_shape = _shape_of(io.V)
                result.v_shape = PASS if v_shape == (n,) or (len(v_shape) == 2 and v_shape[1] == n) else FAIL
            except Exception:
                result.v_shape = FAIL
    else:
        result.y_shape = FAIL if io.Y is not None else SKIPPED
        result.v_shape = FAIL if io.V is not None else SKIPPED

    required_failures = [
        result.z_is_2d == FAIL,
        result.z_is_square == FAIL,
        result.x_length_matches == FAIL,
        result.sectors_length_matches == FAIL,
        result.non_numeric,
        bool(result.nan_exists),
        bool(result.inf_exists),
        result.duplicate_sector_ids is True,
        not _alignment_is_safe(
            result.row_column_labels_match,
            result.normalized_row_column_labels_match,
        ),
        not _alignment_is_safe(
            result.z_row_labels_match_sectors,
            result.normalized_z_row_labels_match_sectors,
        ),
        not _alignment_is_safe(
            result.z_column_labels_match_sectors,
            result.normalized_z_column_labels_match_sectors,
        ),
        not _alignment_is_safe(result.x_labels_match, result.normalized_x_labels_match),
        not _alignment_is_safe(result.y_labels_match, result.normalized_y_labels_match),
        not _alignment_is_safe(result.v_labels_match, result.normalized_v_labels_match),
        bool(core_normalized_duplicates or accounting_normalized_duplicates),
        result.y_shape == FAIL,
        result.v_shape == FAIL,
    ]
    result.status = FAIL if any(required_failures) else PASS
    return result, arrays
