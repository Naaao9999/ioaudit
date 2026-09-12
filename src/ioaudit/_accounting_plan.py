"""Compile declared IO accounting semantics into reusable calculation plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ._balance_core import (
    inflow_adjustment,
    normalize_tolerance,
    outflow_adjustment,
    output_adjustment_vector,
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
    uses: frozenset[str] = frozenset()


@dataclass
class AccountingPlan:
    """Validated inputs and equations shared by all residual diagnostics."""

    y: np.ndarray | None = None
    v: np.ndarray | None = None
    output_adjustment: np.ndarray | None = None
    output: BalanceSidePlan = field(
        default_factory=lambda: BalanceSidePlan(axis=1)
    )
    input: BalanceSidePlan = field(
        default_factory=lambda: BalanceSidePlan(axis=0)
    )
    tolerance: dict[str, float] | None = None
    notes: list[str] = field(default_factory=list)


def _has_component_risk(components: Any, field_name: str) -> bool:
    if components is None:
        return False
    for collection_name in ("double_count_risk", "component_label_risks"):
        for item in getattr(components, collection_name, []) or []:
            if item.get("field") == field_name:
                return True
    return False


def _sum_vectors(*values: np.ndarray) -> np.ndarray:
    """Add accounting offsets while converting overflow into a finite-check result."""

    with np.errstate(over="ignore", invalid="ignore"):
        result = np.asarray(values[0], dtype=float).copy()
        for value in values[1:]:
            result = result + np.asarray(value, dtype=float)
    return result


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


_OUTPUT_TRADE_LABELS = frozenset(
    {
        "imports",
        "international imports",
        "imports of goods and services",
        "interregional inflows",
        "combined inflows",
        "移入",
        "輸入",
        "移輸入",
        "exports",
        "international exports",
        "exports of goods and services",
        "interregional outflows",
        "combined outflows",
        "移出",
        "輸出",
        "移輸出",
    }
)


def _output_adjustment_component_labels(value: Any) -> list[Any] | None:
    """Return semantic component labels for a two-dimensional adjustment block."""

    if value is None:
        return None
    columns = getattr(value, "columns", None)
    if columns is None:
        return None
    labels = list(columns)
    return labels if labels and all(isinstance(label, str) for label in labels) else None


def _output_adjustment_trade_conflict(io: Any, value: Any) -> str | None:
    """Reject ambiguous overlap between output adjustments and trade flows."""

    trade = getattr(io, "trade", None)
    if trade is None or not trade.has_any or value is None:
        return None
    labels = _output_adjustment_component_labels(value)
    if labels is None:
        return (
            "output_adjustments were supplied with TradeFlows but their "
            "component labels are unavailable; possible trade double-counting "
            "cannot be ruled out"
        )
    from .structure import _normalize_label

    normalized = {_normalize_label(label) for label in labels}
    overlaps = sorted(normalized & _OUTPUT_TRADE_LABELS)
    if overlaps:
        return (
            "output_adjustments overlap with declared trade component(s): "
            + ", ".join(overlaps)
        )
    return None


def _append_output_adjustment(
    side: BalanceSidePlan,
    adjustment: np.ndarray | None,
) -> BalanceSidePlan:
    """Add a validated signed output adjustment to an available identity."""

    if adjustment is None or not side.available:
        return side
    side.offset = _sum_vectors(side.offset, adjustment)
    side.uses = frozenset((*side.uses, "output_adjustments"))
    side.equation = f"{side.equation} + output_adjustments (signed)"
    return side


def _resolve_output(
    io: Any,
    *,
    y: np.ndarray | None,
    y_reason: str | None,
    convention: AccountingConvention,
    n: int,
    sectors: list[Any],
    plan: AccountingPlan,
    output_adjustment: np.ndarray | None,
    output_adjustment_reason: str | None,
) -> BalanceSidePlan:
    side = BalanceSidePlan(axis=1)
    if y is None:
        side.reason = y_reason or "Y is unavailable"
        return side

    output_representation = convention.output_representation
    raw_output_adjustment = getattr(io, "output_adjustments", None)
    if output_representation == "unknown":
        side.reason = "output_representation='unknown'; output-side adjustments are not declared"
        return side
    if output_representation == "complete" and raw_output_adjustment is not None:
        side.reason = (
            output_adjustment_reason
            or "output_adjustments were supplied but output_representation='complete'"
        )
        return side
    if output_representation == "adjustments_required":
        if raw_output_adjustment is None:
            side.reason = "output_adjustments are required but were not supplied"
            return side
        if output_adjustment is None:
            side.reason = output_adjustment_reason or "output_adjustments are unavailable"
            return side

    representation = convention.trade_representation
    if convention.transaction_scope == "total":
        # ``unknown`` means that no conflicting declaration was made.  An
        # explicit separate/outflows-in-Y declaration conflicts with a total
        # transaction table and is therefore kept auditable as SKIPPED.
        if representation in {"separate", "outflows_in_Y"}:
            side.reason = (
                "transaction_scope='total' is incompatible with the declared "
                f"trade_representation={representation!r}"
            )
            side.equation = (
                "SKIPPED because transaction_scope='total' does not "
                "support explicitly declared "
                f"trade_representation={representation!r}"
            )
            return side
        side.available = True
        side.offset = y
        side.equation = "x = row_sum(Z) + row_sum(Y)"
        side.uses = frozenset({"Y"})
        plan.notes.append("inflow_sign not applicable")
        if getattr(io, "trade", None) is not None and io.trade.has_any:
            plan.notes.append(
                "trade flows were supplied but excluded by the total transaction scope"
            )
        return _append_output_adjustment(side, output_adjustment)

    if convention.transaction_scope == "unknown":
        side.reason = "transaction_scope is unknown"
        return side
    if convention.import_treatment == "unknown":
        side.reason = "import_treatment is unknown"
        return side
    if representation == "unknown":
        side.reason = "trade_representation is unknown"
        return side
    if convention.import_treatment == "none" and representation != "embedded":
        side.reason = (
            "import_treatment='none' is incompatible with the declared "
            f"trade_representation={representation!r}"
        )
        side.equation = (
            "SKIPPED because import_treatment='none' does not support "
            "explicitly declared "
            f"trade_representation={representation!r}"
        )
        return side
    if convention.import_treatment == "none":
        side.available = True
        side.offset = y
        side.equation = "x = row_sum(Z) + row_sum(Y)"
        side.uses = frozenset({"Y"})
        plan.notes.append("inflow_sign not applicable")
        plan.notes.append("outflow_sign not applicable")
        if getattr(io, "trade", None) is not None and io.trade.has_any:
            plan.notes.append(
                "trade flows were supplied but excluded because import_treatment='none'"
            )
        return _append_output_adjustment(side, output_adjustment)
    if representation == "embedded":
        side.available = True
        side.offset = y
        side.equation = "x = row_sum(Z) + row_sum(Y) (trade embedded in Y)"
        side.uses = frozenset({"Y"})
        plan.notes.append("inflow_sign not applicable")
        plan.notes.append("outflow_sign not applicable")
        if getattr(io, "trade", None) is not None and io.trade.has_any:
            plan.notes.append(
                "trade flows were supplied but excluded because trade_representation='embedded'"
            )
        return _append_output_adjustment(side, output_adjustment)

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

    if representation == "outflows_in_Y":
        side.available = True
        side.offset = _sum_vectors(y, signed_inflow)
        side.uses = frozenset({"Y", "inflows"})
        side.equation = (
            "x = row_sum(Z) + row_sum(Y) + inflow (signed)"
            if convention.inflow_sign == "negative"
            else "x = row_sum(Z) + row_sum(Y) - inflow (positive magnitude)"
        )
        plan.notes.append("outflow_sign not applicable")
        return _append_output_adjustment(side, output_adjustment)
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

    side.available = True
    side.offset = _sum_vectors(y, signed_inflow, signed_outflow)
    side.uses = frozenset({"Y", "inflows", "outflows"})
    inflow_term = (
        f"- inflow ({inflow_label}, positive magnitude)"
        if convention.inflow_sign == "positive"
        else f"+ inflow ({inflow_label}, negative signed)"
    )
    outflow_term = (
        f"+ outflow ({outflow_label}, positive magnitude)"
        if convention.outflow_sign == "positive"
        else f"- outflow ({outflow_label}, negative signed)"
    )
    side.equation = (
        f"x = row_sum(Z) + row_sum(Y) {outflow_term} {inflow_term}"
    )
    return _append_output_adjustment(side, output_adjustment)


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
    adjustment, reason, _source, note = resolve_input_adjustment(io, n=n)
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
        if _source is not None:
            side.reason = (
                "input-side adjustment was supplied but input_representation='complete'; "
                "the adjustment's relationship to V is ambiguous"
            )
            return side
        side.available = True
        side.offset = v
        side.equation = "x = column_sum(Z) + column_sum(V)"
        side.uses = frozenset({"V"})
        return side
    if representation == "adjustments_required":
        if adjustment is None:
            side.reason = reason or "input_adjustments are unavailable"
            return side
        side.available = True
        side.offset = _sum_vectors(v, adjustment)
        side.equation = "x = column_sum(Z) + column_sum(V) + input_adjustment"
        side.uses = frozenset({"V", "input_adjustments"})
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
        tolerance=normalize_tolerance(tolerance),
    )
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
    output_adjustment_raw = getattr(io, "output_adjustments", None)
    if _has_component_risk(components, "output_adjustments"):
        plan.output_adjustment = None
        output_adjustment_reason = (
            "output_adjustments contains an ambiguous subtotal or component label"
        )
        output_note = None
    else:
        plan.output_adjustment, output_adjustment_reason, output_note = output_adjustment_vector(
            output_adjustment_raw,
            name="output_adjustments",
            n=n,
            sectors=sectors,
        )
    if output_note:
        plan.notes.append(output_note)
    if output_adjustment_raw is not None:
        conflict_reason = _output_adjustment_trade_conflict(
            io, output_adjustment_raw
        )
        if conflict_reason:
            plan.output_adjustment = None
            output_adjustment_reason = conflict_reason
            plan.notes.append(conflict_reason)
        elif plan.output_adjustment is None and output_adjustment_reason:
            plan.notes.append(output_adjustment_reason)
    if y_reason and plan.y is None:
        plan.notes.append(y_reason)
    if v_reason and plan.v is None:
        plan.notes.append(v_reason)
    if convention is None:
        reason = "AccountingConvention was not supplied"
        plan.output.reason = reason
        plan.input.reason = reason
        return plan
    plan.output = _resolve_output(
        io,
        y=plan.y,
        y_reason=y_reason,
        convention=convention,
        n=n,
        sectors=sectors,
        plan=plan,
        output_adjustment=plan.output_adjustment,
        output_adjustment_reason=output_adjustment_reason,
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
