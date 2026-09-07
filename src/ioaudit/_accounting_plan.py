"""Compile declared IO accounting semantics into reusable calculation plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ._balance_core import (
    inflow_adjustment,
    normalize_tolerance,
    outflow_adjustment,
    resolve_input_adjustment,
    trade_side,
    vector,
)
from .conventions import AccountingConvention
from .structure import _all_finite, _core_inputs_are_safe, _shape_of


@dataclass
class BalanceSidePlan:
    """One compiled accounting identity."""

    available: bool = False
    axis: int = 0
    offset: np.ndarray | None = None
    equation: str = ""
    reason: str | None = None


@dataclass
class AccountingPlan:
    """Validated inputs and equations shared by all residual diagnostics."""

    x: np.ndarray | None = None
    y: np.ndarray | None = None
    v: np.ndarray | None = None
    input_adjustment: np.ndarray | None = None
    inflow_adjustment: np.ndarray | None = None
    outflow_adjustment: np.ndarray | None = None
    output: BalanceSidePlan = field(
        default_factory=lambda: BalanceSidePlan(axis=1)
    )
    input: BalanceSidePlan = field(
        default_factory=lambda: BalanceSidePlan(axis=0)
    )
    tolerance: dict[str, float] | None = None
    convention: AccountingConvention | None = None
    input_adjustment_source: str | None = None
    inflow_label: str | None = None
    outflow_label: str | None = None
    inflows_used: bool = False
    outflows_used: bool = False
    input_adjustment_applied: bool = False
    input_adjustments_used: bool = False
    inflow_adjustment_applied: bool = False
    outflow_adjustment_applied: bool = False
    notes: list[str] = field(default_factory=list)


def _has_component_risk(components: Any, field_name: str) -> bool:
    if components is None:
        return False
    for collection_name in ("double_count_risk", "component_label_risks"):
        for item in getattr(components, collection_name, []) or []:
            if item.get("field") == field_name:
                return True
    return False


def _validated_component(
    value: Any,
    *,
    field_name: str,
    n: int,
    sectors: list[Any],
    components: Any,
) -> tuple[np.ndarray | None, str | None]:
    if _has_component_risk(components, field_name):
        return (
            None,
            f"{field_name} contains an ambiguous subtotal or component label",
        )
    return vector(value, expected=field_name, n=n, sectors=sectors)


def _resolve_output(
    io: Any,
    *,
    y: np.ndarray | None,
    y_reason: str | None,
    convention: AccountingConvention,
    n: int,
    sectors: list[Any],
    plan: AccountingPlan,
) -> BalanceSidePlan:
    side = BalanceSidePlan(axis=1)
    if y is None:
        side.reason = y_reason or "Y is unavailable"
        return side

    representation = convention.trade_representation
    if convention.transaction_scope == "total":
        # ``unknown`` means that no conflicting declaration was made.  An
        # explicit separate/outflows-in-Y declaration conflicts with a total
        # transaction table and is therefore kept auditable as SKIPPED.
        if representation != "embedded":
            side.reason = (
                "transaction_scope='total' is incompatible with the declared "
                f"trade_representation={representation!r}"
            )
            side.equation = (
                "output: SKIPPED because transaction_scope='total' requires "
                "trade_representation='embedded'"
            )
            return side
        side.available = True
        side.offset = y
        side.equation = "x = row_sum(Z) + row_sum(Y)"
        plan.notes.append("inflow_sign not applicable")
        if getattr(io, "trade", None) is not None and io.trade.has_any:
            plan.notes.append(
                "trade flows were supplied but excluded by the total transaction scope"
            )
        return side

    if convention.transaction_scope == "unknown":
        side.reason = "transaction_scope is unknown"
        return side
    if convention.import_treatment == "unknown":
        side.reason = "import_treatment is unknown"
        return side
    if representation == "unknown":
        side.reason = "trade_representation is unknown"
        return side
    if convention.import_treatment == "none" or representation == "embedded":
        side.available = True
        side.offset = y
        side.equation = (
            "x = row_sum(Z) + row_sum(Y)"
            if convention.import_treatment == "none"
            else "x = row_sum(Z) + row_sum(Y) (trade embedded in Y)"
        )
        plan.notes.append("inflow_sign not applicable")
        plan.notes.append("outflow_sign not applicable")
        if getattr(io, "trade", None) is not None and io.trade.has_any:
            plan.notes.append(
                "trade flows were supplied but excluded because trade_representation='embedded'"
            )
        return side

    trade = getattr(io, "trade", None)
    inflows, reason, inflow_label = trade_side(
        trade,
        side="inflows",
        scope=convention.external_flow_scope,
        n=n,
        sectors=sectors,
    )
    if inflows is None:
        side.reason = reason
        return side
    signed_inflow = inflow_adjustment(inflows, convention.inflow_sign)
    if signed_inflow is None:
        side.reason = "inflow_sign='unknown'; no sign inference is performed"
        return side

    plan.inflows_used = True
    plan.inflow_adjustment_applied = True
    plan.inflow_adjustment = signed_inflow
    plan.inflow_label = inflow_label
    if representation == "outflows_in_Y":
        side.available = True
        side.offset = y + signed_inflow
        side.equation = (
            "x = row_sum(Z) + row_sum(Y) + inflow (signed)"
            if convention.inflow_sign == "negative"
            else "x = row_sum(Z) + row_sum(Y) - inflow (positive magnitude)"
        )
        plan.notes.append("outflow_sign not applicable")
        return side
    if representation != "separate":
        side.reason = f"unsupported trade_representation={representation!r}"
        return side

    outflows, reason, outflow_label = trade_side(
        trade,
        side="outflows",
        scope=convention.external_flow_scope,
        n=n,
        sectors=sectors,
    )
    if outflows is None:
        side.reason = reason
        return side
    signed_outflow = outflow_adjustment(outflows, convention.outflow_sign)
    if signed_outflow is None:
        side.reason = "outflow_sign='unknown'; no sign inference is performed"
        return side

    plan.outflows_used = True
    plan.outflow_adjustment_applied = True
    plan.outflow_adjustment = signed_outflow
    plan.outflow_label = outflow_label
    side.available = True
    side.offset = y + signed_inflow + signed_outflow
    side.equation = (
        f"x = row_sum(Z) + row_sum(Y) + outflow ({outflow_label}) "
        f"- inflow ({inflow_label})"
    )
    return side


def _resolve_input(
    io: Any,
    *,
    v: np.ndarray | None,
    v_reason: str | None,
    convention: AccountingConvention,
    n: int,
    sectors: list[Any],
    plan: AccountingPlan,
) -> BalanceSidePlan:
    side = BalanceSidePlan(axis=0)
    if v is None:
        side.reason = v_reason or "V is unavailable"
        return side
    adjustment, reason, source, note = resolve_input_adjustment(io, n=n)
    if source is not None:
        plan.input_adjustment_source = source
    if note:
        plan.notes.append(note)

    representation = convention.input_representation
    if representation == "unknown":
        side.reason = (
            "input_representation='unknown'; the completeness of V and any "
            "input-side adjustments is not declared"
        )
        return side
    if representation == "complete":
        if source is not None:
            side.reason = (
                "input-side adjustment was supplied but input_representation='complete'; "
                "the adjustment's relationship to V is ambiguous"
            )
            return side
        side.available = True
        side.offset = v
        side.equation = "x = column_sum(Z) + column_sum(V)"
        return side
    if representation == "adjustments_required":
        if adjustment is None:
            side.reason = reason or "input_adjustments are unavailable"
            return side
        plan.input_adjustment = adjustment
        plan.input_adjustment_applied = True
        plan.input_adjustments_used = source == "input_adjustments"
        side.available = True
        side.offset = v + adjustment
        side.equation = "x = column_sum(Z) + column_sum(V) + input_adjustment"
        return side
    side.reason = f"unsupported input_representation={representation!r}"
    return side


def compile_accounting_plan(
    io: Any,
    *,
    z: Any,
    x: np.ndarray | None,
    convention: AccountingConvention | None,
    sectors: list[Any],
    components: Any = None,
    structure: Any = None,
    tolerance: dict[str, float] | None = None,
) -> AccountingPlan:
    """Resolve all declared accounting inputs exactly once."""

    plan = AccountingPlan(
        x=np.asarray(x, dtype=float).reshape(-1) if x is not None else None,
        tolerance=normalize_tolerance(tolerance),
        convention=convention,
    )
    if convention is None:
        reason = "AccountingConvention was not supplied"
        plan.output.reason = reason
        plan.input.reason = reason
        return plan
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
        or (structure is not None and not _core_inputs_are_safe(structure))
    ):
        reason = "Z, x, or their sector labels are not safely aligned"
        plan.output.reason = reason
        plan.input.reason = reason
        return plan

    n = z_shape[0]
    plan.y, y_reason = _validated_component(
        getattr(io, "Y", None),
        field_name="Y",
        n=n,
        sectors=sectors,
        components=components,
    )
    plan.v, v_reason = _validated_component(
        getattr(io, "V", None),
        field_name="V",
        n=n,
        sectors=sectors,
        components=components,
    )
    if y_reason and plan.y is None:
        plan.notes.append(y_reason)
    if v_reason and plan.v is None:
        plan.notes.append(v_reason)
    plan.output = _resolve_output(
        io,
        y=plan.y,
        y_reason=y_reason,
        convention=convention,
        n=n,
        sectors=sectors,
        plan=plan,
    )
    plan.input = _resolve_input(
        io,
        v=plan.v,
        v_reason=v_reason,
        convention=convention,
        n=n,
        sectors=sectors,
        plan=plan,
    )
    return plan


__all__ = [
    "AccountingPlan",
    "BalanceSidePlan",
    "compile_accounting_plan",
]
