"""Diagnostics for row/column orientation and sector order."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ._accounting_plan import AccountingPlan, compile_accounting_plan
from ._residuals import evaluate_residual, residual_for_side
from .structure import (
    _alignment_is_safe,
    _core_inputs_are_safe,
    _labels,
    _same_labels,
    _same_normalized_labels,
    _shape_of,
)


@dataclass
class OrientationDiagnostics:
    """Evidence about the supplied orientation; no transposition is performed."""

    status: str = "SKIPPED"
    row_labels_match_columns: bool | None = None
    normalized_row_labels_match_columns: bool | None = None
    sector_order_consistent: bool | None = None
    normalized_sector_order_consistent: bool | None = None
    x_alignment: bool | None = None
    normalized_x_alignment: bool | None = None
    possible_transpose: bool | None = None
    current_orientation_accounting_residual: float | None = None
    transposed_orientation_accounting_residual: float | None = None
    comparison_available: bool = False
    evidence: list[str] = field(default_factory=list)


def _score(
    z: Any,
    x: np.ndarray,
    plan: AccountingPlan,
    tolerance: dict[str, float] | None = None,
) -> tuple[float | None, bool | None]:
    """Score one orientation using the already compiled accounting plan."""

    scores: list[float] = []
    within_tolerance: list[bool] = []
    for side in (plan.output, plan.input):
        residual = residual_for_side(z, x, side)
        if residual is None:
            continue
        evaluation = evaluate_residual(residual, x, tolerance)
        scores.append(evaluation.max_relative)
        if tolerance is not None and evaluation.allowed is not None:
            within_tolerance.append(bool(np.all(evaluation.absolute <= evaluation.allowed)))
    return (
        max(scores) if scores else None,
        all(within_tolerance) if tolerance is not None and within_tolerance else None,
    )


def diagnose_orientation(
    io: Any,
    z: np.ndarray | None,
    x: np.ndarray | None,
    structure: Any,
    components: Any = None,
    tolerance: dict[str, float] | None = None,
    *,
    plan: AccountingPlan | None = None,
) -> OrientationDiagnostics:
    """Compare current and transposed accounting evidence when available."""

    result = OrientationDiagnostics()
    z_shape = _shape_of(z) if z is not None else ()
    if (
        z is None
        or x is None
        or len(z_shape) != 2
        or z_shape[0] != z_shape[1]
        or len(x) != z_shape[0]
    ):
        result.evidence.append("orientation requires a numeric square Z and aligned x")
        return result
    z_index, z_columns = _labels(io.Z)
    if z_index is not None and z_columns is not None:
        result.row_labels_match_columns = _same_labels(z_index, z_columns)
        result.normalized_row_labels_match_columns = _same_normalized_labels(
            z_index, z_columns
        )
        result.sector_order_consistent = (
            len(io.sectors) == z_shape[0]
            and all(a == b for a, b in zip(z_index, io.sectors))
            and all(a == b for a, b in zip(z_columns, io.sectors))
        )
        result.normalized_sector_order_consistent = (
            _same_normalized_labels(z_index, list(io.sectors))
            and _same_normalized_labels(z_columns, list(io.sectors))
            if len(io.sectors) == z_shape[0]
            else False
        )
    else:
        result.row_labels_match_columns = None
        result.normalized_row_labels_match_columns = None
        result.sector_order_consistent = len(io.sectors) == z.shape[0]
        result.normalized_sector_order_consistent = result.sector_order_consistent
    x_index, _ = _labels(io.x)
    result.x_alignment = (
        all(a == b for a, b in zip(x_index, io.sectors))
        if x_index is not None and len(x_index) == len(io.sectors)
        else (len(x) == len(io.sectors) if x_index is None else False)
    )
    result.normalized_x_alignment = (
        _same_normalized_labels(x_index, list(io.sectors))
        if x_index is not None and len(x_index) == len(io.sectors)
        else (len(x) == len(io.sectors) if x_index is None else False)
    )

    if not _core_inputs_are_safe(structure):
        result.evidence.append(
            "core Z/x values or sector labels are not safely aligned; orientation comparison is SKIPPED"
        )
        result.status = "FAIL"
        return result

    if io.accounting is None:
        result.evidence.append("AccountingConvention was not supplied")
        result.status = (
            "FAIL"
            if not _alignment_is_safe(
                result.sector_order_consistent,
                result.normalized_sector_order_consistent,
            )
            or not _alignment_is_safe(
                result.x_alignment, result.normalized_x_alignment
            )
            else "PASS"
        )
        return result

    if plan is None:
        plan = compile_accounting_plan(
            io,
            z=z,
            x=x,
            convention=io.accounting,
            sectors=list(io.sectors),
            components=components,
            structure=structure,
            tolerance=tolerance,
        )
    if not plan.output.available:
        result.evidence.append(
            "output accounting evidence is unavailable: "
            + (plan.output.reason or "unknown reason")
        )
    if not plan.input.available:
        result.evidence.append(
            "input accounting evidence is unavailable: "
            + (plan.input.reason or "unknown reason")
        )
    if not plan.output.available and not plan.input.available:
        result.evidence.append("orientation residual comparison is unavailable")
        result.status = (
            "FAIL"
            if not _alignment_is_safe(
                result.sector_order_consistent,
                result.normalized_sector_order_consistent,
            )
            or not _alignment_is_safe(
                result.x_alignment, result.normalized_x_alignment
            )
            else "PASS"
        )
        return result

    current_score, current_within_tolerance = _score(
        z, x, plan, tolerance=tolerance
    )
    transposed_score, transposed_within_tolerance = _score(
        z.T, x, plan, tolerance=tolerance
    )
    result.current_orientation_accounting_residual = current_score
    result.transposed_orientation_accounting_residual = transposed_score
    current = result.current_orientation_accounting_residual
    transposed = result.transposed_orientation_accounting_residual
    result.comparison_available = current is not None and transposed is not None
    if result.comparison_available:
        if (
            tolerance is not None
            and current_within_tolerance is True
            and transposed_within_tolerance is True
        ):
            result.possible_transpose = None
            result.evidence.append(
                "current and transposed residuals are both within the declared tolerance"
            )
        elif np.isfinite(current) and not np.isfinite(transposed):
            result.possible_transpose = False
        elif np.isfinite(transposed) and not np.isfinite(current):
            result.possible_transpose = True
        else:
            margin = max(1e-12, 1e-6 * max(1.0, abs(current), abs(transposed)))
            if transposed + margin < current:
                result.possible_transpose = True
            elif current + margin < transposed:
                result.possible_transpose = False
            else:
                result.possible_transpose = None
        if result.possible_transpose is None:
            result.evidence.append("current and transposed residuals are indistinguishable")
        elif result.possible_transpose:
            result.evidence.append("transposed orientation has the lower accounting residual")
        else:
            result.evidence.append("current orientation has the lower accounting residual")
    else:
        result.evidence.append("orientation residual comparison is unavailable")
    result.status = (
        "FAIL"
        if not _alignment_is_safe(
            result.sector_order_consistent,
            result.normalized_sector_order_consistent,
        )
        or not _alignment_is_safe(result.x_alignment, result.normalized_x_alignment)
        else "PASS"
    )
    return result
