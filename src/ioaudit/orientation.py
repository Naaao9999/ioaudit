"""Diagnostics for row/column orientation and sector order."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ._balance_core import (
    axis_sum as _axis_sum,
    inflow_adjustment as _inflow_adjustment,
    outflow_adjustment as _outflow_adjustment,
    resolve_input_adjustment as _resolve_input_adjustment,
    trade_side as _trade_side,
    vector as _vector,
)
from .structure import (
    _alignment_is_safe,
    _all_finite,
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
    f: np.ndarray | None,
    v: np.ndarray | None,
    io: Any,
) -> float | None:
    scores: list[float] = []
    convention = io.accounting
    if f is not None:
        base = _axis_sum(z, 1) + f
        residual = None
        trade = getattr(io, "trade", None)
        representation = convention.trade_representation
        inflow_sign = convention.inflow_sign
        if (
            representation == "unknown"
            or convention.transaction_scope == "unknown"
            or convention.import_treatment == "unknown"
        ):
            residual = None
        elif convention.transaction_scope == "total" or convention.import_treatment == "none":
            residual = x - base
        elif representation == "embedded":
            residual = x - base
        else:
            inflows, _, _ = _trade_side(
                trade,
                side="inflows",
                scope=convention.external_flow_scope,
                n=z.shape[0],
                sectors=list(io.sectors),
            )
            inflow_adjustment = (
                _inflow_adjustment(inflows, inflow_sign)
                if inflows is not None
                else None
            )
            if inflow_adjustment is not None:
                if representation == "outflows_in_Y":
                    residual = x - (base + inflow_adjustment)
                else:
                    outflows, _, _ = _trade_side(
                        trade,
                        side="outflows",
                        scope=convention.external_flow_scope,
                        n=z.shape[0],
                        sectors=list(io.sectors),
                    )
                    outflow_adjustment = (
                        _outflow_adjustment(outflows, convention.outflow_sign)
                        if outflows is not None
                        else None
                    )
                    if outflow_adjustment is not None:
                        residual = x - (base + outflow_adjustment + inflow_adjustment)
        if residual is not None:
            abs_residual = np.abs(residual)
            relative = np.zeros_like(abs_residual)
            nz = x != 0
            np.divide(abs_residual, np.abs(x), out=relative, where=nz)
            relative[(~nz) & (abs_residual != 0)] = np.inf
            scores.append(float(np.max(relative)) if relative.size else 0.0)
    input_residual = None
    if v is not None:
        input_representation = convention.input_representation
        adjustment, _, adjustment_source, _ = _resolve_input_adjustment(
            io, n=z.shape[0]
        )
        if input_representation == "complete" and adjustment_source is None:
            input_residual = x - (_axis_sum(z, 0) + v)
        elif input_representation == "adjustments_required" and adjustment is not None:
            input_residual = x - (_axis_sum(z, 0) + v + adjustment)
    if input_residual is not None:
        residual = input_residual
        abs_residual = np.abs(residual)
        relative = np.zeros_like(abs_residual)
        nz = x != 0
        np.divide(abs_residual, np.abs(x), out=relative, where=nz)
        relative[(~nz) & (abs_residual != 0)] = np.inf
        scores.append(float(np.max(relative)) if relative.size else 0.0)
    return max(scores) if scores else None


def diagnose_orientation(
    io: Any,
    z: np.ndarray | None,
    x: np.ndarray | None,
    structure: Any,
    components: Any = None,
) -> OrientationDiagnostics:
    """Compare current and transposed accounting evidence when available."""

    result = OrientationDiagnostics()
    z_shape = _shape_of(z) if z is not None else ()
    if z is None or x is None or len(z_shape) != 2 or z_shape[0] != z_shape[1] or len(x) != z_shape[0]:
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
    component_risks = getattr(components, "double_count_risk", []) if components is not None else []
    y_subtotal_risk = any(item.get("field") == "Y" for item in component_risks)
    v_subtotal_risk = any(item.get("field") == "V" for item in component_risks)
    f, _ = (
        (None, "Y subtotal risk")
        if y_subtotal_risk
        else _vector(io.Y, expected="Y", n=z.shape[0], sectors=list(io.sectors))
    )
    v, _ = (
        (None, "V subtotal risk")
        if v_subtotal_risk
        else _vector(io.V, expected="V", n=z.shape[0], sectors=list(io.sectors))
    )
    if y_subtotal_risk:
        result.evidence.append("Y subtotal/total risk excluded from orientation comparison")
    if v_subtotal_risk:
        result.evidence.append("V subtotal/total risk excluded from orientation comparison")
    if (f is None and v is None) or not _all_finite(z) or not _all_finite(x):
        result.evidence.append("Y or V is unavailable for orientation comparison")
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

    result.current_orientation_accounting_residual = _score(z, x, f, v, io)
    result.transposed_orientation_accounting_residual = _score(z.T, x, f, v, io)
    current = result.current_orientation_accounting_residual
    transposed = result.transposed_orientation_accounting_residual
    result.comparison_available = current is not None and transposed is not None
    if result.comparison_available:
        if np.isfinite(current) and not np.isfinite(transposed):
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
