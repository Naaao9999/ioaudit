"""Shared, validated inputs for one audit run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._accounting_plan import AccountingPlan
from ._residuals import PlanResiduals, evaluate_plan
from .structure import _core_inputs_are_safe


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Validated inputs and shared accounting state for one audit run.

    Individual diagnostics consume this object instead of re-reading raw
    ``IOSystem`` fields or independently deciding whether positional
    calculations are safe.
    """

    io: Any
    structure: Any
    components: Any
    z: Any
    x: Any
    dependent_z: Any
    dependent_x: Any
    sectors: tuple[Any, ...]
    plan: AccountingPlan
    baseline: PlanResiduals
    core_inputs_safe: bool

    @classmethod
    def build(
        cls,
        io: Any,
        *,
        structure: Any,
        components: Any,
        arrays: dict[str, Any],
        plan: AccountingPlan,
    ) -> "AuditContext":
        """Build a context from structure and the compiled accounting plan."""

        z = arrays.get("Z")
        x = arrays.get("x")
        core_inputs_safe = _core_inputs_are_safe(structure)
        dependent_z = z if core_inputs_safe else None
        dependent_x = x if core_inputs_safe else None
        return cls(
            io=io,
            structure=structure,
            components=components,
            z=z,
            x=x,
            dependent_z=dependent_z,
            dependent_x=dependent_x,
            sectors=tuple(io.sectors),
            plan=plan,
            baseline=evaluate_plan(dependent_z, dependent_x, plan),
            core_inputs_safe=core_inputs_safe,
        )


__all__ = ["AuditContext"]
