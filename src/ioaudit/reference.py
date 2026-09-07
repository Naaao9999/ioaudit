"""Validation against externally supplied A and Leontief matrices."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .structure import _as_array, _labels, _numeric_array


@dataclass
class MatrixComparison:
    """Numerical and structural comparison for one reference matrix."""

    status: str = "SKIPPED"
    calculated: np.ndarray | None = None
    reference: np.ndarray | None = None
    max_absolute_difference: float | None = None
    mean_absolute_difference: float | None = None
    rmse: float | None = None
    relative_difference: float | None = None
    difference_class: str | None = None
    shape_consistency: bool | None = None
    label_consistency: bool | None = None
    reason: str | None = None


@dataclass
class ReferenceDiagnostics:
    """Comparisons for optional A_reference and L_reference."""

    status: str = "SKIPPED"
    A: MatrixComparison = field(default_factory=MatrixComparison)
    L: MatrixComparison = field(default_factory=MatrixComparison)


def _label_consistency(reference: Any, target: Any, sectors: list[Any]) -> bool | None:
    ref_index, ref_columns = _labels(reference)
    if ref_index is None or ref_columns is None:
        return None
    target_index, target_columns = _labels(target)
    expected_index = target_index if target_index is not None else sectors
    expected_columns = target_columns if target_columns is not None else sectors
    return (
        len(ref_index) == len(expected_index)
        and len(ref_columns) == len(expected_columns)
        and all(a == b for a, b in zip(ref_index, expected_index))
        and all(a == b for a, b in zip(ref_columns, expected_columns))
    )


def _compare(calculated: np.ndarray | None, reference: Any, target: Any, sectors: list[Any]) -> MatrixComparison:
    result = MatrixComparison()
    if reference is None:
        return result
    try:
        ref, bad = _numeric_array(reference)
    except Exception as exc:
        result.status = "FAIL"
        result.reason = f"reference could not be read: {exc}"
        return result
    if ref is None or bad:
        result.status = "FAIL"
        result.reason = "reference contains non-numeric or missing values"
        return result
    ref_array = _as_array(ref)
    result.reference = ref_array
    if calculated is None:
        result.reason = "calculated matrix is unavailable"
        return result
    calculated_array = _as_array(calculated)
    result.calculated = calculated_array
    result.shape_consistency = tuple(calculated_array.shape) == tuple(ref_array.shape)
    result.label_consistency = _label_consistency(reference, target, sectors)
    if not result.shape_consistency:
        result.status = "FAIL"
        result.reason = "reference and calculated matrix shapes differ"
        return result
    if not np.isfinite(ref_array).all() or not np.isfinite(calculated_array).all():
        result.status = "FAIL"
        result.reason = "reference or calculated matrix contains NaN/Inf"
        return result
    with np.errstate(over="ignore", invalid="ignore"):
        difference = calculated_array - ref_array
    if not np.isfinite(difference).all():
        result.status = "FAIL"
        result.reason = "reference difference exceeds floating-point range"
        return result
    absolute = np.abs(difference)
    scale = float(np.max(absolute)) if absolute.size else 0.0
    scaled = absolute / scale if scale else np.zeros_like(absolute)
    result.max_absolute_difference = scale
    result.mean_absolute_difference = scale * float(np.mean(scaled)) if scaled.size else 0.0
    result.rmse = scale * float(np.sqrt(np.mean(scaled**2))) if scaled.size else 0.0
    ref_scale = float(np.max(np.abs(ref_array))) if ref_array.size else 0.0
    if ref_scale and scale:
        # Normalize both norms before squaring. Their unscaled norms can
        # overflow even when the ratio and every reported metric are finite.
        numerator_mantissa, numerator_exponent = np.frexp(scale)
        denominator_mantissa, denominator_exponent = np.frexp(ref_scale)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            result.relative_difference = float(
                np.ldexp(
                    (np.linalg.norm(scaled) / np.linalg.norm(ref_array / ref_scale))
                    * numerator_mantissa / denominator_mantissa,
                    numerator_exponent - denominator_exponent,
                )
            )
        if not np.isfinite(result.relative_difference):
            result.status = "FAIL"
            result.reason = "relative reference difference exceeds floating-point range"
            return result
    else:
        result.relative_difference = 0.0 if not scale else float("inf")
    exact = bool(
        np.all(
            absolute
            <= np.finfo(float).eps * np.maximum(1.0, np.abs(ref_array))
        )
    )
    if result.label_consistency is False:
        result.status = "FAIL"
        result.difference_class = "label_mismatch"
    elif exact:
        result.status = "PASS"
        result.difference_class = "exact"
    else:
        result.status = "AVAILABLE"
        result.difference_class = "numeric_difference"
    return result


def diagnose_reference(
    io: Any,
    a: np.ndarray | None,
    l: np.ndarray | None,
) -> ReferenceDiagnostics:
    """Compare calculated matrices with optional references."""

    result = ReferenceDiagnostics()
    result.A = _compare(a, io.A_reference, io.Z, list(io.sectors))
    result.L = _compare(l, io.L_reference, io.Z, list(io.sectors))
    comparisons = [item for item in (result.A, result.L) if item.status != "SKIPPED"]
    if not comparisons:
        return result
    if any(item.status == "FAIL" for item in comparisons):
        result.status = "FAIL"
    elif any(item.status == "AVAILABLE" for item in comparisons):
        result.status = "AVAILABLE"
    else:
        result.status = "PASS"
    return result
