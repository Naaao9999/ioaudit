"""Accounting identity diagnostics for a single IO table."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ._accounting_plan import AccountingPlan, compile_accounting_plan
from ._residuals import PlanResiduals, evaluate_plan, evaluate_residual
from .conventions import AccountingConvention
from .structure import _shape_of


@dataclass
class BalanceDiagnostics:
    """Residual metrics for one compiled accounting identity."""

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
    inflow_adjustment_applied: bool = False
    outflow_adjustment_applied: bool = False
    input_adjustment_applied: bool = False
    input_adjustments_used: bool = False
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
    """Convert a numeric residual into the public balance result."""

    evaluation = evaluate_residual(residual, x, tolerance)
    return BalanceDiagnostics(
        status=evaluation.status,
        residual_class=evaluation.residual_class,
        equation=equation,
        sector_residual=evaluation.residual.tolist(),
        absolute_residual=evaluation.absolute.tolist(),
        relative_residual=evaluation.relative.tolist(),
        mae=evaluation.mae,
        rmse=evaluation.rmse,
        max_absolute_residual=evaluation.max_absolute,
        max_relative_residual=evaluation.max_relative,
    )


def _side_balance(
    side: Any,
    residual: np.ndarray | None,
    x: np.ndarray | None,
    tolerance: dict[str, float] | None,
) -> BalanceDiagnostics:
    """Build a public result from one plan side, including skip reasons."""

    result = BalanceDiagnostics(
        equation=getattr(side, "equation", ""),
        reason=getattr(side, "reason", None),
    )
    if residual is None or x is None or not getattr(side, "available", False):
        return result
    return _balance(residual, x, getattr(side, "equation", ""), tolerance)


def _formula(plan: AccountingPlan) -> str:
    output = plan.output.equation or (
        f"SKIPPED because {plan.output.reason or 'output identity is unavailable'}"
    )
    input_side = plan.input.equation or (
        f"SKIPPED because {plan.input.reason or 'input identity is unavailable'}"
    )
    return f"output: {output}; input: {input_side}"


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
    plan: AccountingPlan | None = None,
    baseline: PlanResiduals | None = None,
) -> AccountingDiagnostics:
    """Report residuals from a compiled accounting plan.

    ``plan`` is optional for callers of this lower-level function.  The
    top-level audit compiles it once and passes it to every dependent
    diagnostic.
    """

    if plan is None:
        plan = compile_accounting_plan(
            io,
            z=z,
            x=x,
            convention=convention,
            sectors=sectors,
            components=components,
            structure=structure,
            tolerance=tolerance,
        )
    result = AccountingDiagnostics(
        convention=convention.to_dict() if convention is not None else None,
        tolerance=plan.tolerance,
        formula=_formula(plan),
        notes=list(plan.notes),
        inflow_adjustment_applied=plan.inflow_adjustment_applied,
        outflow_adjustment_applied=plan.outflow_adjustment_applied,
        input_adjustment_applied=plan.input_adjustment_applied,
        input_adjustments_used=plan.input_adjustments_used,
        inflows_used=plan.inflows_used,
        outflows_used=plan.outflows_used,
    )
    if convention is None:
        result.notes.append(
            "AccountingConvention was not supplied; accounting checks are SKIPPED"
        )
        return result

    residuals = baseline if baseline is not None else evaluate_plan(z, x, plan)
    result.output_balance = _side_balance(
        plan.output, residuals.output, plan.x, plan.tolerance
    )
    result.input_balance = _side_balance(
        plan.input, residuals.input, plan.x, plan.tolerance
    )
    result.formula = _formula(plan)
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
    residuals_relative = [
        balance.max_relative_residual
        for balance in available
        if balance.max_relative_residual is not None
    ]
    result.max_relative_residual = (
        max(residuals_relative) if residuals_relative else None
    )

    z_shape = _shape_of(z) if z is not None else ()
    n = z_shape[0] if len(z_shape) == 2 else 0
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


__all__ = [
    "AccountingDiagnostics",
    "BalanceDiagnostics",
    "diagnose_accounting",
]
