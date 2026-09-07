"""Shared residual calculations for accounting diagnostics.

The public report classes keep the human-readable representation of a
residual.  This module contains the numeric representation used internally by
accounting, orientation, and scale diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ._balance_core import axis_sum


@dataclass(frozen=True)
class ResidualEvaluation:
    """Numeric metrics for one residual vector."""

    residual: np.ndarray
    absolute: np.ndarray
    relative: np.ndarray
    allowed: np.ndarray | None
    excess: np.ndarray
    status: str
    residual_class: str
    mae: float
    rmse: float
    max_absolute: float
    max_relative: float


@dataclass(frozen=True)
class PlanResiduals:
    """Residual vectors for the two sides of an accounting plan."""

    input: np.ndarray | None = None
    output: np.ndarray | None = None


def relative_residual(residual: Any, x: Any) -> np.ndarray:
    """Return absolute residual divided by the absolute output vector."""

    values = np.asarray(residual, dtype=float)
    denominator = np.asarray(x, dtype=float)
    absolute = np.abs(values)
    relative = np.zeros_like(absolute)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        np.divide(
            absolute,
            np.abs(denominator),
            out=relative,
            where=denominator != 0,
        )
    relative[(denominator == 0) & (absolute != 0)] = np.inf
    return relative


def tolerance_envelope(
    x: Any, tolerance: dict[str, float] | None
) -> np.ndarray | None:
    """Return the declared absolute tolerance for every sector."""

    if tolerance is None:
        return None
    denominator = np.asarray(x, dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        return np.maximum.reduce(
            (
                np.full_like(denominator, float(tolerance.get("absolute", 0.0))),
                float(tolerance.get("relative", 0.0)) * np.abs(denominator),
                np.full_like(
                    denominator, float(tolerance.get("rounding_unit", 0.0))
                ),
            )
        )


def evaluate_residual(
    residual: Any,
    x: Any,
    tolerance: dict[str, float] | None = None,
) -> ResidualEvaluation:
    """Evaluate a residual with the shared tolerance and metric definitions."""

    values = np.asarray(residual, dtype=float).reshape(-1)
    denominator = np.asarray(x, dtype=float).reshape(-1)
    absolute = np.abs(values)
    relative = relative_residual(values, denominator)
    allowed = tolerance_envelope(denominator, tolerance)

    with np.errstate(over="ignore", invalid="ignore"):
        exact = bool(
            np.all(
                absolute
                <= np.finfo(float).eps * np.maximum(1.0, np.abs(denominator))
            )
        )
    if allowed is None:
        excess = values.copy()
        status = "PASS" if exact else "AVAILABLE"
        residual_class = "exact" if exact else "nonzero"
    else:
        with np.errstate(over="ignore", invalid="ignore"):
            excess_abs = np.maximum(absolute - allowed, 0.0)
            excess = np.copysign(excess_abs, values)
            within_tolerance = bool(np.all(absolute <= allowed))
        if exact:
            status = "PASS"
            residual_class = "exact"
        elif within_tolerance:
            status = "PASS"
            residual_class = "rounding_level"
        else:
            status = "FAIL"
            residual_class = "outside_tolerance"

    if absolute.size:
        with np.errstate(over="ignore", invalid="ignore"):
            scale = float(np.max(absolute))
            if scale == 0.0:
                rmse = 0.0
            elif np.isfinite(scale):
                rmse = float(scale * np.sqrt(np.mean((values / scale) ** 2)))
            else:
                rmse = float("inf")
        finite_relative = relative[np.isfinite(relative)]
        max_relative = (
            float(np.max(relative))
            if relative.size and np.isinf(relative).any()
            else float(np.max(finite_relative))
            if finite_relative.size
            else float("inf")
        )
        max_absolute = float(np.max(absolute))
        mae = float(np.mean(absolute)) if np.isfinite(absolute).all() else float("inf")
    else:
        mae = rmse = max_absolute = max_relative = 0.0

    return ResidualEvaluation(
        residual=values,
        absolute=absolute,
        relative=relative,
        allowed=allowed,
        excess=excess,
        status=status,
        residual_class=residual_class,
        mae=mae,
        rmse=rmse,
        max_absolute=max_absolute,
        max_relative=max_relative,
    )


def residual_for_side(z: Any, x: Any, side: Any) -> np.ndarray | None:
    """Evaluate ``x - (axis_sum(Z) + offset)`` for one compiled side."""

    if side is None or not getattr(side, "available", False):
        return None
    offset = getattr(side, "offset", None)
    if offset is None:
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        return np.asarray(x, dtype=float) - (
            axis_sum(z, int(side.axis)) + np.asarray(offset, dtype=float)
        )


def evaluate_plan(
    z: Any,
    x: Any,
    plan: Any,
) -> PlanResiduals:
    """Evaluate both sides of a compiled accounting plan."""

    if z is None or x is None or plan is None:
        return PlanResiduals()
    return PlanResiduals(
        input=residual_for_side(z, x, getattr(plan, "input", None)),
        output=residual_for_side(z, x, getattr(plan, "output", None)),
    )


__all__ = [
    "PlanResiduals",
    "ResidualEvaluation",
    "evaluate_plan",
    "evaluate_residual",
    "relative_residual",
    "residual_for_side",
    "tolerance_envelope",
]
