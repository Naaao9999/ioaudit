"""Candidate diagnostics for powers-of-ten scale errors.

This module tests hypothetical scale factors against already-declared
accounting identities.  It never changes the supplied IO system and never
selects a correction for the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .accounting import _axis_sum, _vector
from .structure import (
    _all_finite,
    _as_array,
    _dimension_vector,
    _is_sparse,
    _numeric_array,
    _shape_of,
)


DEFAULT_SCALE_FACTORS = tuple(
    float(10.0**exponent) for exponent in range(-6, 7) if exponent != 0
)
_MIN_IMPROVEMENT = 0.5
_MIN_GLOBAL_COVERAGE = 0.75
_MAX_OPPOSITE_SIDE_DEGRADATION = 0.10
_ROBUST_Z = 6.0


@dataclass
class ScaleDiagnostics:
    """Evidence for possible global, row, column, and cell scale errors."""

    status: str = "SKIPPED"
    candidate_factors: list[float] = field(
        default_factory=lambda: list(DEFAULT_SCALE_FACTORS)
    )
    possible_global_scale_mismatches: list[dict[str, Any]] = field(default_factory=list)
    possible_row_scale_errors: list[dict[str, Any]] = field(default_factory=list)
    possible_column_scale_errors: list[dict[str, Any]] = field(default_factory=list)
    possible_cell_scale_errors: list[dict[str, Any]] = field(default_factory=list)
    robust_outliers: list[dict[str, Any]] = field(default_factory=list)
    minimum_improvement: float = _MIN_IMPROVEMENT
    minimum_global_coverage: float = _MIN_GLOBAL_COVERAGE
    maximum_opposite_side_degradation: float = _MAX_OPPOSITE_SIDE_DEGRADATION
    tolerance: dict[str, float] | None = None
    rounding_context_available: bool = False
    cell_status: str = "SKIPPED"
    cell_reason: str | None = "scale diagnostics unavailable"
    reason: str | None = None

    @property
    def total_candidates(self) -> int:
        """Return the number of reported scale candidates."""

        return sum(
            len(items)
            for items in (
                self.possible_global_scale_mismatches,
                self.possible_row_scale_errors,
                self.possible_column_scale_errors,
                self.possible_cell_scale_errors,
            )
        )


def _balance_residual(balance: Any) -> np.ndarray | None:
    if balance is None or getattr(balance, "status", "SKIPPED") == "SKIPPED":
        return None
    try:
        residual = np.asarray(balance.sector_residual, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    return residual if residual.size and np.isfinite(residual).all() else None


def _metric(residuals: list[np.ndarray | None], x: np.ndarray) -> float | None:
    available = [value for value in residuals if value is not None]
    if not available:
        return None
    combined = np.concatenate(available)
    if not np.isfinite(combined).all():
        return None
    denominator = max(float(np.linalg.norm(x)), 1.0)
    return float(np.linalg.norm(combined) / denominator)


def _evidence_residual(
    residual: np.ndarray | None,
    x: np.ndarray,
    tolerance: dict[str, float] | None,
) -> np.ndarray | None:
    """Return residual remaining outside a declared accounting envelope.

    The raw accounting residual is retained by the accounting diagnostics.
    Scale diagnostics use only the excess beyond ``max(absolute,
    relative * abs(x), rounding_unit)`` when a tolerance is declared.  This
    prevents a rounding-sized difference from becoming scale-error evidence.
    """

    if residual is None:
        return None
    values = np.asarray(residual, dtype=float)
    if tolerance is None:
        return values.copy()
    allowed = np.maximum.reduce(
        (
            np.full_like(values, float(tolerance.get("absolute", 0.0))),
            float(tolerance.get("relative", 0.0)) * np.abs(x),
            np.full_like(values, float(tolerance.get("rounding_unit", 0.0))),
        )
    )
    excess = np.maximum(np.abs(values) - allowed, 0.0)
    return np.copysign(excess, values)


def _improvement(before: float, after: float) -> float | None:
    if not np.isfinite(before) or not np.isfinite(after) or before <= 0.0:
        return None
    return float((before - after) / before)


def _coverage(
    before: list[np.ndarray | None], after: list[np.ndarray | None]
) -> float | None:
    """Measure how broadly a hypothetical factor improves the balances."""

    pairs = [
        (left, right)
        for left, right in zip(before, after)
        if left is not None and right is not None
    ]
    if not pairs:
        return None
    total = sum(len(left) for left, _ in pairs)
    if total == 0:
        return None
    improved = sum(
        int(value)
        for left, right in pairs
        for value in (np.abs(right) < np.abs(left))
    )
    return float(improved / total)


def _evidence_level(improvement: float) -> str:
    if improvement >= 0.99:
        return "strong"
    if improvement >= 0.75:
        return "likely"
    return "possible"


def _side_constraint(
    before: float | None, after: float | None
) -> tuple[bool, float | None, float | None, bool]:
    """Allow a candidate only when the opposite balance does not worsen materially."""

    if before is None or after is None:
        return True, None, None, False
    if not np.isfinite(before) or not np.isfinite(after):
        return False, None, None, True
    if before == 0.0:
        allowed = np.finfo(float).eps
        return after <= allowed, None, 0.0 if after == 0.0 else float("inf"), True
    degradation = (after - before) / before
    return (
        degradation <= _MAX_OPPOSITE_SIDE_DEGRADATION,
        float(-degradation),
        float(degradation),
        True,
    )


def _label(sectors: list[Any], index: int) -> Any:
    return sectors[index] if 0 <= index < len(sectors) else index


def _cell_values(z: Any):
    if _is_sparse(z):
        coo = z.tocoo(copy=True)
        coo.sum_duplicates()
        for row, column, value in zip(coo.row, coo.col, np.asarray(coo.data)):
            if np.isfinite(value) and value != 0:
                yield int(row), int(column), float(value)
        return
    array = np.asarray(z, dtype=float)
    for row, column in np.argwhere(np.isfinite(array) & (array != 0)):
        yield int(row), int(column), float(array[row, column])


def _reference_array(io: Any, shape: tuple[int, ...]) -> np.ndarray | None:
    reference = getattr(io, "A_reference", None)
    if reference is None:
        return None
    try:
        numeric, bad = _numeric_array(reference)
        if numeric is None or bad:
            return None
        array = _as_array(numeric).astype(float, copy=False)
    except (TypeError, ValueError):
        return None
    return array if tuple(array.shape) == shape and np.isfinite(array).all() else None


def _global_candidates(
    *,
    x: np.ndarray,
    row_sum: np.ndarray,
    column_sum: np.ndarray,
    f: np.ndarray | None,
    v: np.ndarray | None,
    input_residual: np.ndarray | None,
    output_residual: np.ndarray | None,
    sectors: list[Any],
    factors: tuple[float, ...],
    tolerance: dict[str, float] | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    field_availability = {
        "x": input_residual is not None or output_residual is not None,
        "Z": input_residual is not None or output_residual is not None,
        "Y": output_residual is not None and f is not None,
        "V": input_residual is not None and v is not None,
    }
    for field_name, available in field_availability.items():
        if not available:
            continue
        if field_name in {"x", "Z"}:
            selected_before = [input_residual, output_residual]
            balances = [
                name
                for name, residual in (
                    ("input", input_residual),
                    ("output", output_residual),
                )
                if residual is not None
            ]
        elif field_name == "Y":
            selected_before = [output_residual]
            balances = ["output"]
        else:
            selected_before = [input_residual]
            balances = ["input"]
        selected_before_evidence = [
            _evidence_residual(residual, x, tolerance)
            for residual in selected_before
        ]
        before_raw = _metric(selected_before, x)
        before = _metric(selected_before_evidence, x)
        if before is None or before == 0.0:
            continue
        for factor in factors:
            candidate_input = input_residual.copy() if input_residual is not None else None
            candidate_output = output_residual.copy() if output_residual is not None else None
            delta = factor - 1.0
            if field_name == "x":
                if candidate_input is not None:
                    candidate_input += delta * x
                if candidate_output is not None:
                    candidate_output += delta * x
            elif field_name == "Z":
                if candidate_input is not None:
                    candidate_input -= delta * column_sum
                if candidate_output is not None:
                    candidate_output -= delta * row_sum
            elif field_name == "Y" and candidate_output is not None and f is not None:
                candidate_output -= delta * f
            elif field_name == "V" and candidate_input is not None and v is not None:
                candidate_input -= delta * v
            selected_after_raw = [candidate_input, candidate_output]
            if field_name in {"x", "Z"}:
                selected_after = [
                    _evidence_residual(residual, x, tolerance)
                    for residual in selected_after_raw
                ]
            elif field_name == "Y":
                selected_after_raw = [candidate_output]
                selected_after = [
                    _evidence_residual(candidate_output, x, tolerance)
                ]
            else:
                selected_after_raw = [candidate_input]
                selected_after = [
                    _evidence_residual(candidate_input, x, tolerance)
                ]
            after = _metric(selected_after, x)
            after_raw = _metric(selected_after_raw, x)
            if after is None:
                continue
            coverage = _coverage(selected_before_evidence, selected_after)
            if coverage is None or coverage < _MIN_GLOBAL_COVERAGE:
                continue
            improvement = _improvement(before, after)
            if improvement is None or improvement < _MIN_IMPROVEMENT:
                continue
            candidates.append(
                {
                    "field": field_name,
                    "candidate_factor": factor,
                    "residual_before": before_raw,
                    "residual_after": after_raw,
                    "evidence_residual_before": before,
                    "evidence_residual_after": after,
                    "improvement": improvement,
                    "coverage": coverage,
                    "affected_balances": balances,
                    "evidence_level": _evidence_level(improvement),
                }
            )
    candidates.sort(key=lambda item: (-item["improvement"], item["field"], item["candidate_factor"]))
    return candidates


def _row_candidates(
    *,
    z: Any,
    x: np.ndarray,
    row_sum: np.ndarray,
    input_residual: np.ndarray | None,
    output_residual: np.ndarray | None,
    sectors: list[Any],
    factors: tuple[float, ...],
    tolerance: dict[str, float] | None,
) -> list[dict[str, Any]]:
    if output_residual is None:
        return []
    candidates: list[dict[str, Any]] = []
    input_before = _metric(
        [_evidence_residual(input_residual, x, tolerance)], x
    )
    output_evidence = _evidence_residual(output_residual, x, tolerance)
    if output_evidence is None:
        return []
    for index, total in enumerate(row_sum):
        raw_before = abs(float(output_residual[index]))
        before = abs(float(output_evidence[index]))
        if not np.isfinite(before) or before == 0.0 or not np.isfinite(total):
            continue
        row_values = _dimension_vector(z, 0, index)
        for factor in factors:
            raw_after = abs(float(output_residual[index] - (factor - 1.0) * total))
            candidate_output = output_residual.copy()
            candidate_output[index] -= (factor - 1.0) * total
            candidate_output_evidence = _evidence_residual(
                candidate_output, x, tolerance
            )
            if candidate_output_evidence is None:
                continue
            after = abs(float(candidate_output_evidence[index]))
            improvement = _improvement(before, after)
            if improvement is None or improvement < _MIN_IMPROVEMENT:
                continue
            candidate_input = (
                input_residual - (factor - 1.0) * row_values
                if input_residual is not None
                else None
            )
            input_after = _metric(
                [_evidence_residual(candidate_input, x, tolerance)], x
            )
            side_ok, side_improvement, side_degradation, side_available = _side_constraint(
                input_before, input_after
            )
            if not side_ok:
                continue
            candidates.append(
                {
                    "index": index,
                    "sector": _label(sectors, index),
                    "candidate_factor": factor,
                    "residual_before": raw_before,
                    "residual_after": raw_after,
                    "evidence_residual_before": before,
                    "evidence_residual_after": after,
                    "improvement": improvement,
                    "opposite_balance": "input",
                    "opposite_balance_before": input_before,
                    "opposite_balance_after": input_after,
                    "opposite_balance_improvement": side_improvement,
                    "opposite_balance_degradation": side_degradation,
                    "evidence_level": (
                        _evidence_level(improvement) if side_available else "one_sided"
                    ),
                    "opposite_balance_available": side_available,
                }
            )
    candidates.sort(key=lambda item: (-item["improvement"], item["index"], item["candidate_factor"]))
    return candidates


def _column_candidates(
    *,
    z: Any,
    x: np.ndarray,
    column_sum: np.ndarray,
    output_residual: np.ndarray | None,
    input_residual: np.ndarray | None,
    sectors: list[Any],
    factors: tuple[float, ...],
    tolerance: dict[str, float] | None,
) -> list[dict[str, Any]]:
    if input_residual is None:
        return []
    candidates: list[dict[str, Any]] = []
    output_before = _metric(
        [_evidence_residual(output_residual, x, tolerance)], x
    )
    input_evidence = _evidence_residual(input_residual, x, tolerance)
    if input_evidence is None:
        return []
    for index, total in enumerate(column_sum):
        raw_before = abs(float(input_residual[index]))
        before = abs(float(input_evidence[index]))
        if not np.isfinite(before) or before == 0.0 or not np.isfinite(total):
            continue
        column_values = _dimension_vector(z, 1, index)
        for factor in factors:
            raw_after = abs(float(input_residual[index] - (factor - 1.0) * total))
            candidate_input = input_residual.copy()
            candidate_input[index] -= (factor - 1.0) * total
            candidate_input_evidence = _evidence_residual(
                candidate_input, x, tolerance
            )
            if candidate_input_evidence is None:
                continue
            after = abs(float(candidate_input_evidence[index]))
            improvement = _improvement(before, after)
            if improvement is None or improvement < _MIN_IMPROVEMENT:
                continue
            candidate_output = (
                output_residual - (factor - 1.0) * column_values
                if output_residual is not None
                else None
            )
            output_after = _metric(
                [_evidence_residual(candidate_output, x, tolerance)], x
            )
            side_ok, side_improvement, side_degradation, side_available = _side_constraint(
                output_before, output_after
            )
            if not side_ok:
                continue
            candidates.append(
                {
                    "index": index,
                    "sector": _label(sectors, index),
                    "candidate_factor": factor,
                    "residual_before": raw_before,
                    "residual_after": raw_after,
                    "evidence_residual_before": before,
                    "evidence_residual_after": after,
                    "improvement": improvement,
                    "opposite_balance": "output",
                    "opposite_balance_before": output_before,
                    "opposite_balance_after": output_after,
                    "opposite_balance_improvement": side_improvement,
                    "opposite_balance_degradation": side_degradation,
                    "evidence_level": (
                        _evidence_level(improvement) if side_available else "one_sided"
                    ),
                    "opposite_balance_available": side_available,
                }
            )
    candidates.sort(key=lambda item: (-item["improvement"], item["index"], item["candidate_factor"]))
    return candidates


def _cell_candidates(
    *,
    z: Any,
    x: np.ndarray,
    input_residual: np.ndarray | None,
    output_residual: np.ndarray | None,
    sectors: list[Any],
    factors: tuple[float, ...],
    a_reference: np.ndarray | None,
    tolerance: dict[str, float] | None,
) -> list[dict[str, Any]]:
    if input_residual is None or output_residual is None:
        return []
    candidates: list[dict[str, Any]] = []
    input_evidence = _evidence_residual(input_residual, x, tolerance)
    output_evidence = _evidence_residual(output_residual, x, tolerance)
    if input_evidence is None or output_evidence is None:
        return []
    for row, column, value in _cell_values(z):
        raw_before_output = abs(float(output_residual[row]))
        raw_before_input = abs(float(input_residual[column]))
        before_output = abs(float(output_evidence[row]))
        before_input = abs(float(input_evidence[column]))
        if (
            not np.isfinite(before_output)
            or not np.isfinite(before_input)
            or before_output == 0.0
            or before_input == 0.0
            or x[column] == 0.0
        ):
            continue
        for factor in factors:
            candidate_output = output_residual.copy()
            candidate_input = input_residual.copy()
            candidate_output[row] -= (factor - 1.0) * value
            candidate_input[column] -= (factor - 1.0) * value
            candidate_output_evidence = _evidence_residual(
                candidate_output, x, tolerance
            )
            candidate_input_evidence = _evidence_residual(
                candidate_input, x, tolerance
            )
            if candidate_output_evidence is None or candidate_input_evidence is None:
                continue
            after_output = abs(float(candidate_output_evidence[row]))
            after_input = abs(float(candidate_input_evidence[column]))
            raw_after_output = abs(float(candidate_output[row]))
            raw_after_input = abs(float(candidate_input[column]))
            output_improvement = _improvement(before_output, after_output)
            input_improvement = _improvement(before_input, after_input)
            if (
                output_improvement is None
                or input_improvement is None
                or output_improvement < _MIN_IMPROVEMENT
                or input_improvement < _MIN_IMPROVEMENT
            ):
                continue
            item: dict[str, Any] = {
                "row_index": row,
                "row": _label(sectors, row),
                "column_index": column,
                "column": _label(sectors, column),
                "value": value,
                "candidate_factor": factor,
                "candidate_value": value * factor,
                "output_residual_before": raw_before_output,
                "output_residual_after": raw_after_output,
                "input_residual_before": raw_before_input,
                "input_residual_after": raw_after_input,
                "output_evidence_residual_before": before_output,
                "output_evidence_residual_after": after_output,
                "input_evidence_residual_before": before_input,
                "input_evidence_residual_after": after_input,
                "output_residual_improvement": output_improvement,
                "input_residual_improvement": input_improvement,
                "evidence_level": _evidence_level(
                    min(output_improvement, input_improvement)
                ),
            }
            if a_reference is not None:
                current_a = value / x[column]
                reference_before = abs(float(current_a - a_reference[row, column]))
                reference_after = abs(float(factor * current_a - a_reference[row, column]))
                reference_improvement = _improvement(reference_before, reference_after)
                item["A_reference_difference_before"] = reference_before
                item["A_reference_difference_after"] = reference_after
                item["A_reference_improvement"] = reference_improvement
                if reference_improvement is not None and reference_improvement >= _MIN_IMPROVEMENT:
                    item["reference_evidence"] = "A_reference also improves"
                    if item["evidence_level"] == "strong":
                        item["evidence_level"] = "strong_with_A_reference"
            candidates.append(item)
    candidates.sort(
        key=lambda item: (
            -min(item["output_residual_improvement"], item["input_residual_improvement"]),
            item["row_index"],
            item["column_index"],
            item["candidate_factor"],
        )
    )
    return candidates


def _robust_outliers(
    residual: np.ndarray | None,
    balance: str,
    sectors: list[Any],
) -> list[dict[str, Any]]:
    if residual is None:
        return []
    absolute = np.abs(residual)
    median = float(np.median(absolute))
    mad = float(np.median(np.abs(absolute - median)))
    if mad == 0.0:
        return []
    robust_z = 0.67448975 * (absolute - median) / mad
    return [
        {
            "balance": balance,
            "index": int(index),
            "sector": _label(sectors, int(index)),
            "absolute_residual": float(absolute[index]),
            "robust_z": float(robust_z[index]),
            "threshold": _ROBUST_Z,
        }
        for index in np.flatnonzero(robust_z >= _ROBUST_Z)
    ]


def diagnose_scale(
    z: Any,
    x: np.ndarray | None,
    io: Any,
    accounting: Any,
    sectors: list[Any],
    factors: tuple[float, ...] = DEFAULT_SCALE_FACTORS,
) -> ScaleDiagnostics:
    """Find scale factors that materially reduce declared balance residuals."""

    result = ScaleDiagnostics(candidate_factors=list(factors))
    z_shape = _shape_of(z) if z is not None else ()
    if (
        z is None
        or x is None
        or len(z_shape) != 2
        or z_shape[0] != z_shape[1]
        or getattr(x, "ndim", None) != 1
        or len(x) != z_shape[0]
        or not _all_finite(z)
        or not _all_finite(x)
    ):
        result.reason = "scale diagnostics require finite numeric square Z and aligned x"
        return result
    if accounting is None:
        result.reason = "AccountingConvention was not supplied"
        return result

    input_residual = _balance_residual(getattr(accounting, "input_balance", None))
    output_residual = _balance_residual(getattr(accounting, "output_balance", None))
    if input_residual is None and output_residual is None:
        result.reason = "no auditable accounting residual was available"
        return result

    x_array = np.asarray(x, dtype=float).reshape(-1)
    tolerance = getattr(accounting, "tolerance", None)
    result.tolerance = dict(tolerance) if tolerance is not None else None
    result.rounding_context_available = tolerance is not None
    if tolerance is not None:
        result.cell_status = "AVAILABLE"
        result.cell_reason = None
    else:
        result.cell_status = "SKIPPED"
        result.cell_reason = "rounding context unavailable"
    try:
        row_sum = _axis_sum(z, 1)
        column_sum = _axis_sum(z, 0)
        f, _ = _vector(getattr(io, "Y", None), expected="Y", n=z_shape[0])
        v, _ = _vector(getattr(io, "V", None), expected="V", n=z_shape[0])
    except (TypeError, ValueError, FloatingPointError) as exc:
        result.reason = f"scale diagnostics could not read accounting fields: {exc}"
        return result

    result.possible_global_scale_mismatches = _global_candidates(
        x=x_array,
        row_sum=row_sum,
        column_sum=column_sum,
        f=f,
        v=v,
        input_residual=input_residual,
        output_residual=output_residual,
        sectors=sectors,
        factors=factors,
        tolerance=tolerance,
    )
    result.possible_row_scale_errors = _row_candidates(
        z=z,
        x=x_array,
        row_sum=row_sum,
        input_residual=input_residual,
        output_residual=output_residual,
        sectors=sectors,
        factors=factors,
        tolerance=tolerance,
    )
    result.possible_column_scale_errors = _column_candidates(
        z=z,
        x=x_array,
        column_sum=column_sum,
        output_residual=output_residual,
        input_residual=input_residual,
        sectors=sectors,
        factors=factors,
        tolerance=tolerance,
    )
    a_reference = _reference_array(io, z_shape)
    if tolerance is not None:
        result.possible_cell_scale_errors = _cell_candidates(
            z=z,
            x=x_array,
            input_residual=input_residual,
            output_residual=output_residual,
            sectors=sectors,
            factors=factors,
            a_reference=a_reference,
            tolerance=tolerance,
        )
    result.robust_outliers = _robust_outliers(
        _evidence_residual(output_residual, x_array, tolerance), "output", sectors
    ) + _robust_outliers(
        _evidence_residual(input_residual, x_array, tolerance), "input", sectors
    )
    result.status = "AVAILABLE"
    return result


__all__ = ["ScaleDiagnostics", "diagnose_scale"]
