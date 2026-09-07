"""Accounting identity diagnostics for a single IO table."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ._balance_core import (
    axis_sum as _axis_sum,
    inflow_adjustment as _inflow_adjustment,
    normalize_tolerance as _normalize_tolerance,
    outflow_adjustment as _outflow_adjustment,
    resolve_input_adjustment as _resolve_input_adjustment,
    trade_side as _trade_side,
    vector as _vector,
)
from .conventions import AccountingConvention
from .structure import _all_finite, _core_inputs_are_safe, _shape_of


@dataclass
class BalanceDiagnostics:
    """Residuals for one accounting identity."""

    status: str = "SKIPPED"
    residual_class: str | None = None
    equation: str = ""
    sector_residual: list[float] = field(default_factory=list)
    absolute_residual: list[float] = field(default_factory=list)
    relative_residual: list[float] = field(default_factory=list)
    mae: float | None = None
    rmse: float | None = None
    max_absolute_residual: float | None = None
    max_relative_residual: float | None = None
    reason: str | None = None

    @property
    def sector_level_residual(self) -> list[float]:
        """Alias for the sector-level signed residual vector."""

        return self.sector_residual

    @property
    def MAE(self) -> float | None:
        """Upper-case alias matching the conventional metric name."""

        return self.mae

    @property
    def RMSE(self) -> float | None:
        """Upper-case alias matching the conventional metric name."""

        return self.rmse


@dataclass
class AccountingDiagnostics:
    """Input-side and output-side balance results."""

    status: str = "SKIPPED"
    convention: dict[str, str] | None = None
    formula: str | None = None
    input_balance: BalanceDiagnostics = field(default_factory=BalanceDiagnostics)
    output_balance: BalanceDiagnostics = field(default_factory=BalanceDiagnostics)
    trade_adjusted_input_balance: BalanceDiagnostics = field(default_factory=BalanceDiagnostics)
    by_sector: list[dict[str, Any]] = field(default_factory=list)
    max_relative_residual: float | None = None
    convention_required: bool = True
    import_adjustment_applied: bool = False
    input_adjustment_applied: bool = False
    input_adjustments_used: bool = False
    imports_used: bool = False
    exports_used: bool = False
    inflows_used: bool = False
    outflows_used: bool = False
    tolerance: dict[str, float] | None = None
    notes: list[str] = field(default_factory=list)


def _balance(
    residual: np.ndarray,
    x: np.ndarray,
    equation: str,
    tolerance: dict[str, float] | None = None,
) -> BalanceDiagnostics:
    residual = np.asarray(residual, dtype=float)
    absolute = np.abs(residual)
    relative = np.zeros_like(absolute)
    nonzero_x = x != 0
    np.divide(absolute, np.abs(x), out=relative, where=nonzero_x)
    relative[(~nonzero_x) & (absolute != 0)] = np.inf
    finite_rel = relative[np.isfinite(relative)]
    exact = bool(
        np.all(
            absolute
            <= np.finfo(float).eps * np.maximum(1.0, np.abs(x))
        )
    )
    residual_class = "exact" if exact else "nonzero"
    status = "PASS" if exact else "AVAILABLE"
    if tolerance is not None:
        absolute_limit = float(tolerance.get("absolute", 0.0))
        relative_limit = float(tolerance.get("relative", 0.0))
        rounding_unit = float(tolerance.get("rounding_unit", 0.0))
        allowed = np.maximum(
            np.maximum(absolute_limit, relative_limit * np.abs(x)), rounding_unit
        )
        within_tolerance = bool(np.all(absolute <= allowed))
        if not exact and within_tolerance:
            status = "PASS"
            residual_class = "rounding_level"
        elif not within_tolerance:
            status = "FAIL"
            residual_class = "outside_tolerance"
    return BalanceDiagnostics(
        status=status,
        residual_class=residual_class,
        equation=equation,
        sector_residual=residual.tolist(),
        absolute_residual=absolute.tolist(),
        relative_residual=relative.tolist(),
        mae=float(np.mean(absolute)) if absolute.size else 0.0,
        rmse=float(np.sqrt(np.mean(residual**2))) if residual.size else 0.0,
        max_absolute_residual=float(np.max(absolute)) if absolute.size else 0.0,
        max_relative_residual=float(np.max(finite_rel))
        if finite_rel.size and not np.isinf(relative).any()
        else (float("inf") if relative.size else 0.0),
    )


def diagnose_accounting(
    z: Any,
    x: np.ndarray | None,
    io: Any,
    convention: AccountingConvention | None,
    sectors: list[Any],
    *,
    tolerance: dict[str, float] | None = None,
    components: Any = None,
    structure: Any = None,
) -> AccountingDiagnostics:
    """Compute declared input/output identities without inferring trade."""

    result = AccountingDiagnostics(tolerance=_normalize_tolerance(tolerance))
    if convention is None:
        result.notes.append("AccountingConvention was not supplied; accounting checks are SKIPPED")
        return result
    result.convention = convention.to_dict()
    z_shape = _shape_of(z) if z is not None else ()
    if z is None or x is None or len(z_shape) != 2 or z_shape[0] != z_shape[1] or getattr(x, "ndim", None) != 1 or len(x) != z_shape[0]:
        result.notes.append("Z and x do not have a safe square/numeric shape")
        return result
    if structure is not None and not _core_inputs_are_safe(structure):
        result.notes.append(
            "Z, x, or their sector labels are not safely aligned; accounting checks are SKIPPED"
        )
        return result
    n = z_shape[0]
    if not _all_finite(z) or not _all_finite(x):
        result.notes.append("Z or x contains NaN/Inf")
        return result

    f, y_reason = _vector(
        io.Y, expected="Y", n=n, sectors=sectors
    )
    v, v_reason = _vector(
        io.V, expected="V", n=n, sectors=sectors
    )
    component_risks = getattr(components, "double_count_risk", []) if components is not None else []
    y_subtotal_risk = any(item.get("field") == "Y" for item in component_risks)
    v_subtotal_risk = any(item.get("field") == "V" for item in component_risks)
    if y_subtotal_risk:
        result.notes.append(
            "Y subtotal/total component detected; output balance is SKIPPED rather than auto-excluding a column"
        )
    if v_subtotal_risk:
        result.notes.append(
            "V subtotal/total component detected; input balance is SKIPPED rather than auto-excluding a row"
        )
    trade = getattr(io, "trade", None)
    row_sum = _axis_sum(z, 1)
    output_residual: np.ndarray | None = None
    output_equation = ""
    representation = convention.trade_representation
    inflow_sign = convention.inflow_sign

    if f is None:
        result.formula = "output: SKIPPED because Y is unavailable"
        result.output_balance.reason = y_reason
    elif y_subtotal_risk:
        result.formula = "output: SKIPPED because Y contains a possible subtotal/total component"
        result.output_balance.reason = (
            "Y contains a possible subtotal/total component; the correct component subset was not inferred"
        )
    elif representation == "unknown":
        result.formula = "output: SKIPPED because trade_representation='unknown'"
        result.output_balance.reason = "trade representation in Y is unknown; no output-side inference is performed"
    elif (
        convention.transaction_scope == "unknown"
        or convention.import_treatment == "unknown"
    ):
        result.formula = (
            "output: SKIPPED because transaction_scope or import_treatment is unknown"
        )
        result.output_balance.reason = (
            "transaction_scope/import_treatment is unknown; no output-side accounting equation is inferred"
        )
    elif convention.transaction_scope == "total" or convention.import_treatment == "none":
        result.formula = (
            "output: x = row_sum(Z) + row_sum(Y); "
            "input: x = column_sum(Z) + column_sum(V)"
        )
        output_equation = "x = row_sum(Z) + row_sum(Y)"
        output_residual = x - (row_sum + f)
        if trade is not None and trade.has_any:
            result.notes.append("trade flows were supplied but excluded by the declared scope/treatment")
        result.notes.append("inflow_sign not applicable")
    elif representation == "embedded":
        result.formula = (
            "output: x = row_sum(Z) + row_sum(Y) (trade embedded in Y); "
            "input: x = column_sum(Z) + column_sum(V)"
        )
        output_equation = "x = row_sum(Z) + row_sum(Y)"
        output_residual = x - (row_sum + f)
        result.notes.append("trade flows were supplied but excluded because trade_representation='embedded'") if trade is not None and trade.has_any else None
        result.notes.append("inflow_sign not applicable")
        result.notes.append("outflow_sign not applicable")
    else:
        inflows, inflow_reason, inflow_label = _trade_side(
            trade,
            side="inflows",
            scope=convention.external_flow_scope,
            n=n,
            sectors=sectors,
        )
        if inflows is None:
            result.output_balance.reason = inflow_reason
        else:
            inflow_adjustment = _inflow_adjustment(inflows, inflow_sign)
            if inflow_adjustment is None:
                result.formula = "output: SKIPPED because inflow_sign='unknown'"
                result.output_balance.reason = "inflow_sign='unknown'; no sign inference is performed"
            else:
                result.inflows_used = True
                result.imports_used = True
                if representation == "outflows_in_Y":
                    if inflow_label == "international_imports" and inflow_sign == "negative":
                        output_equation = "x = row_sum(Z) + row_sum(Y) + imports (imports are signed)"
                        result.formula = (
                            "output: x = row_sum(Z) + row_sum(Y) + imports (imports are signed); "
                            "input: x = column_sum(Z) + column_sum(V)"
                        )
                    elif inflow_label == "international_imports" and inflow_sign == "positive":
                        output_equation = "x = row_sum(Z) + row_sum(Y) - imports"
                        result.formula = (
                            "output: x = row_sum(Z) + row_sum(Y) - imports (positive magnitude); "
                            "input: x = column_sum(Z) + column_sum(V)"
                        )
                    else:
                        output_equation = f"x = row_sum(Z) + row_sum(Y) - inflow ({inflow_label})"
                        result.formula = (
                            "output: x = row_sum(Z) + row_sum(Y) - inflow; "
                            "input: x = column_sum(Z) + column_sum(V)"
                        )
                    output_residual = x - (row_sum + f + inflow_adjustment)
                    result.import_adjustment_applied = True
                    result.notes.append("outflow_sign not applicable")
                else:
                    outflows, outflow_reason, outflow_label = _trade_side(
                        trade,
                        side="outflows",
                        scope=convention.external_flow_scope,
                        n=n,
                        sectors=sectors,
                    )
                    if outflows is None:
                        result.output_balance.reason = outflow_reason
                    else:
                        outflow_adjustment = _outflow_adjustment(outflows, convention.outflow_sign)
                        if outflow_adjustment is None:
                            result.formula = "output: SKIPPED because outflow_sign='unknown'"
                            result.output_balance.reason = "outflow_sign='unknown'; no sign inference is performed"
                        else:
                            result.outflows_used = True
                            result.exports_used = True
                            output_equation = (
                                f"x = row_sum(Z) + row_sum(Y) + outflow ({outflow_label}) "
                                f"- inflow ({inflow_label})"
                            )
                            output_residual = x - (row_sum + f + outflow_adjustment + inflow_adjustment)
                            result.formula = (
                                "output: x = row_sum(Z) + row_sum(Y) + outflow - inflow; "
                                "input: x = column_sum(Z) + column_sum(V)"
                            )
                            result.import_adjustment_applied = True
    if result.formula is None:
        result.formula = "output: x = row_sum(Z) + row_sum(Y)"
    if output_residual is not None:
        result.output_balance = _balance(
            output_residual, x, output_equation, result.tolerance
        )

    (
        input_adjustment,
        input_adjustment_reason,
        input_adjustment_source,
        input_adjustment_alignment_note,
    ) = (
        _resolve_input_adjustment(io, n=n)
    )
    input_equation = "input: SKIPPED"
    if v_subtotal_risk:
        result.input_balance.reason = (
            "V contains a possible subtotal/total component; the correct component subset was not inferred"
        )
        input_equation = "input: SKIPPED because V contains a possible subtotal/total component"
    elif v is None:
        result.input_balance.reason = v_reason
        input_equation = "input: SKIPPED because V is unavailable"
    elif convention.input_representation == "unknown":
        result.input_balance.reason = (
            "input_representation='unknown'; the completeness of V and any input-side adjustments is not declared"
        )
        input_equation = "input: SKIPPED because input_representation='unknown'"
    elif convention.input_representation == "complete":
        if input_adjustment_source is not None:
            result.input_balance.reason = (
                "input-side adjustment was supplied but input_representation='complete'; "
                "the adjustment's relationship to V is ambiguous"
            )
            input_equation = "input: SKIPPED because a complete V conflicts with supplied input adjustment"
        else:
            input_equation = "input: x = column_sum(Z) + column_sum(V)"
            result.input_balance = _balance(
                x - (_axis_sum(z, 0) + v),
                x,
                "x = column_sum(Z) + column_sum(V)",
                result.tolerance,
            )
    elif convention.input_representation == "adjustments_required":
        if input_adjustment is None:
            result.input_balance.reason = (
                "input_representation='adjustments_required' but no valid signed "
                "external input adjustment was supplied"
            )
            input_equation = "input: SKIPPED because input-side adjustment is unavailable"
        else:
            result.input_adjustment_applied = True
            result.input_adjustments_used = input_adjustment_source == "input_adjustments"
            input_equation = (
                "input: x = column_sum(Z) + column_sum(V) + input_adjustment"
            )
            result.input_balance = _balance(
                x - (_axis_sum(z, 0) + v + input_adjustment),
                x,
                "x = column_sum(Z) + column_sum(V) + input_adjustment",
                result.tolerance,
            )
    else:
        result.input_balance.reason = (
            f"unsupported input_representation={convention.input_representation!r}"
        )
        input_equation = "input: SKIPPED because input_representation is unsupported"

    if input_adjustment_reason and input_adjustment_source is not None:
        result.notes.append(input_adjustment_reason)
    if input_adjustment_alignment_note:
        result.notes.append(input_adjustment_alignment_note)
    if input_adjustment_source is not None and input_adjustment is None:
        result.input_balance.reason = input_adjustment_reason
    if "input:" in result.formula:
        output_formula = result.formula.split("; input:", 1)[0]
    else:
        output_formula = result.formula
    result.formula = f"{output_formula}; {input_equation}"
    result.trade_adjusted_input_balance.reason = (
        "SKIPPED: product/commodity inflows are not reused as user-specific inputs; "
        "use input_representation='adjustments_required' with an explicit input-side adjustment"
    )

    balances = [result.input_balance, result.output_balance]
    available = [balance for balance in balances if balance.status != "SKIPPED"]
    if not available:
        result.notes.append("Neither an auditable Y nor V was available")
        return result
    if any(balance.status == "FAIL" for balance in available):
        result.status = "FAIL"
    elif len(available) < len(balances):
        result.status = "AVAILABLE"
    elif all(balance.status == "PASS" for balance in available):
        result.status = "PASS"
    else:
        result.status = "AVAILABLE"
    residuals = [balance.max_relative_residual for balance in available if balance.max_relative_residual is not None]
    result.max_relative_residual = max(residuals) if residuals else None
    if len(sectors) != n:
        result.notes.append("by_sector omitted because sector IDs are not aligned with Z")
        return result
    for index, sector in enumerate(sectors):
        row: dict[str, Any] = {"sector": sector}
        if result.input_balance.status != "SKIPPED":
            row["input_residual"] = result.input_balance.sector_residual[index]
            row["input_absolute_residual"] = result.input_balance.absolute_residual[index]
            row["input_relative_residual"] = result.input_balance.relative_residual[index]
        if result.output_balance.status != "SKIPPED":
            row["output_residual"] = result.output_balance.sector_residual[index]
            row["output_absolute_residual"] = result.output_balance.absolute_residual[index]
            row["output_relative_residual"] = result.output_balance.relative_residual[index]
        result.by_sector.append(row)
    return result
