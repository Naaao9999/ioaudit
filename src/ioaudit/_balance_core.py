"""Shared helpers for declared input-output balance calculations.

The accounting, orientation, and scale diagnostics use these helpers so that
they interpret Y, V, trade, and input adjustments in the same way.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .exceptions import IOValidationError
from .structure import (
    _all_finite,
    _labels,
    _numeric_array,
    _same_labels,
    _same_normalized_labels,
    _shape_of,
)


def axis_sum(value: Any, axis: int) -> np.ndarray:
    """Sum a dense or sparse matrix along one axis without densifying input."""

    summed = value.sum(axis=axis)
    return np.asarray(summed, dtype=float).reshape(-1)


def _check_sector_alignment(
    labels: list[Any] | None,
    sectors: list[Any] | None,
    *,
    name: str,
    axis: str,
) -> str | None:
    """Validate a labelled sector axis without reordering source values."""

    if labels is None or sectors is None:
        return None
    exact = _same_labels(labels, sectors)
    normalized = _same_normalized_labels(labels, sectors)
    if exact is False and normalized is not True:
        return f"{name} {axis} do not match sectors in order"
    return None


def vector(
    value: Any,
    *,
    expected: str,
    n: int,
    sectors: list[Any] | None = None,
) -> tuple[np.ndarray | None, str | None]:
    """Read an accounting vector from Y or V using its declared axis."""

    if value is None:
        return None, f"{expected} was not supplied"
    try:
        array, bad = _numeric_array(value)
    except Exception as exc:
        return None, f"{expected} could not be read: {exc}"
    if array is None or bad or not _all_finite(array):
        return None, f"{expected} contains non-numeric or missing values"
    if expected == "Y":
        if getattr(array, "ndim", None) == 1 and array.shape == (n,):
            index, _ = _labels(value)
            alignment_error = _check_sector_alignment(
                index, sectors, name="Y", axis="index"
            )
            if alignment_error:
                return None, alignment_error
            return np.asarray(array, dtype=float), None
        if getattr(array, "ndim", None) == 2 and array.shape[0] == n:
            index, _ = _labels(value)
            alignment_error = _check_sector_alignment(
                index, sectors, name="Y", axis="index"
            )
            if alignment_error:
                return None, alignment_error
            return axis_sum(array, 1), None
        return None, "Y must have shape (n,) or (n, k)"
    if expected == "V":
        if getattr(array, "ndim", None) == 1 and array.shape == (n,):
            index, _ = _labels(value)
            alignment_error = _check_sector_alignment(
                index, sectors, name="V", axis="index"
            )
            if alignment_error:
                return None, alignment_error
            return np.asarray(array, dtype=float), None
        if getattr(array, "ndim", None) == 2 and array.shape[1] == n:
            _, columns = _labels(value)
            alignment_error = _check_sector_alignment(
                columns, sectors, name="V", axis="columns"
            )
            if alignment_error:
                return None, alignment_error
            return axis_sum(array, 0), None
        return None, "V must have shape (n,) or (m, n)"
    return None, f"unsupported accounting input {expected}"


def aggregate_sector_vector(
    value: Any,
    *,
    name: str,
    n: int,
    sectors: list[Any] | None = None,
) -> tuple[np.ndarray | None, str | None]:
    """Read a one-dimensional flow with an explicit sector axis."""

    if value is None:
        return None, f"{name} was not supplied"
    try:
        array, bad = _numeric_array(value)
    except Exception as exc:
        return None, f"{name} could not be read: {exc}"
    if array is None or bad or not _all_finite(array):
        return None, f"{name} contains non-numeric or missing values"
    if getattr(array, "ndim", None) != 1 or array.shape != (n,):
        return None, f"{name} must have explicit shape (n,) for v0.1 accounting"
    index, _ = _labels(value)
    alignment_error = _check_sector_alignment(
        index, sectors, name=name, axis="index"
    )
    if alignment_error:
        return None, alignment_error
    return np.asarray(array, dtype=float), None


def input_adjustment_vector(
    value: Any, *, name: str, n: int, sectors: list[Any]
) -> tuple[np.ndarray | None, str | None, str | None]:
    """Read a signed input adjustment and validate its sector alignment."""

    if value is None:
        return None, f"{name} was not supplied", None
    try:
        array, bad = _numeric_array(value)
    except Exception as exc:
        return None, f"{name} could not be read: {exc}", None
    if array is None or bad or not _all_finite(array):
        return None, f"{name} contains non-numeric or missing values", None

    labels_index, labels_columns = _labels(value)
    shape = _shape_of(array)
    if len(shape) == 1 and shape == (n,):
        alignment_labels = labels_index
    elif len(shape) == 2 and shape[1] == n:
        alignment_labels = labels_columns
    else:
        return None, f"{name} must have shape (n,) or (m, n)", None

    alignment_note = None
    if alignment_labels is not None:
        exact = _same_labels(alignment_labels, sectors)
        normalized = _same_normalized_labels(alignment_labels, sectors)
        if exact is False and normalized is not True:
            axis = "columns" if len(shape) == 2 else "index"
            return (
                None,
                f"{name} {axis} do not match sectors in order; positional use was skipped",
                None,
            )
        if exact is False and normalized is True:
            axis = "columns" if len(shape) == 2 else "index"
            alignment_note = (
                f"{name} {axis} match sectors only after Unicode/whitespace normalization; "
                "values were used in the declared order"
            )

    if len(shape) == 1:
        return np.asarray(array, dtype=float), None, alignment_note
    return axis_sum(array, 0), None, alignment_note


def resolve_input_adjustment(
    io: Any, *, n: int
) -> tuple[np.ndarray | None, str | None, str | None, str | None]:
    """Resolve the single explicit input-adjustments field."""

    value = getattr(io, "input_adjustments", None)
    if value is None:
        return None, "no input adjustment was supplied", None, None
    vector_value, reason, alignment_note = input_adjustment_vector(
        value,
        name="input_adjustments",
        n=n,
        sectors=list(io.sectors),
    )
    return vector_value, reason, "input_adjustments", alignment_note


def trade_side(
    trade: Any,
    *,
    side: str,
    scope: str,
    n: int,
    sectors: list[Any] | None = None,
) -> tuple[np.ndarray | None, str | None, str | None]:
    """Resolve one trade side as a combined or complete split representation."""

    if trade is None:
        return None, f"trade.{side} was not supplied", None
    if scope not in {"international", "interregional", "both"}:
        return None, "external_flow_scope='unknown'; trade scope is not declared", None
    if side == "inflows":
        combined_name = "combined_inflows"
        components = {
            "international": (("international_imports",), "international_imports"),
            "interregional": (("interregional_inflows",), "interregional_inflows"),
            "both": (("interregional_inflows", "international_imports"), "split inflows"),
        }
    else:
        combined_name = "combined_outflows"
        components = {
            "international": (("international_exports",), "international_exports"),
            "interregional": (("interregional_outflows",), "interregional_outflows"),
            "both": (("interregional_outflows", "international_exports"), "split outflows"),
        }
    combined = getattr(trade, combined_name)
    names, label = components[scope]
    present = [getattr(trade, name) is not None for name in names]
    all_split_names = (
        ("interregional_inflows", "international_imports")
        if side == "inflows"
        else ("interregional_outflows", "international_exports")
    )
    if combined is not None and any(
        getattr(trade, name) is not None for name in all_split_names
    ):
        return None, f"combined and split {side} were supplied together", None
    if combined is not None:
        value, reason = aggregate_sector_vector(
            combined, name=f"trade.{combined_name}", n=n, sectors=sectors
        )
        return value, reason, combined_name if value is not None else None
    if not all(present):
        missing = [name for name, is_present in zip(names, present) if not is_present]
        return None, f"missing trade.{side} component(s): {', '.join(missing)}", None
    vectors: list[np.ndarray] = []
    for name in names:
        value, reason = aggregate_sector_vector(
            getattr(trade, name), name=f"trade.{name}", n=n, sectors=sectors
        )
        if value is None:
            return None, reason, None
        vectors.append(value)
    return np.sum(vectors, axis=0), None, label


def inflow_adjustment(raw: np.ndarray, sign: str) -> np.ndarray | None:
    """Convert a declared inflow vector into the signed output equation."""

    if sign == "negative":
        return raw
    if sign == "positive":
        return -raw
    return None


def outflow_adjustment(raw: np.ndarray, sign: str) -> np.ndarray | None:
    """Convert a declared outflow vector into the signed output equation."""

    if sign == "positive":
        return raw
    if sign == "negative":
        return -raw
    return None


def normalize_tolerance(value: Any) -> dict[str, float] | None:
    """Validate and normalize an explicit accounting tolerance mapping."""

    if value is None:
        return None
    if not isinstance(value, dict):
        raise IOValidationError("accounting_tolerance must be a mapping or None")
    allowed = {"absolute", "relative", "rounding_unit"}
    unknown = set(value) - allowed
    if unknown:
        raise IOValidationError(
            "accounting_tolerance has unknown fields: "
            + ", ".join(sorted(map(str, unknown)))
        )
    normalized: dict[str, float] = {}
    for name in allowed:
        raw = value.get(name, 0.0)
        if isinstance(raw, bool):
            raise IOValidationError(
                f"accounting_tolerance.{name} must be finite and non-negative"
            )
        try:
            numeric = float(raw)
        except (TypeError, ValueError) as exc:
            raise IOValidationError(f"accounting_tolerance.{name} must be numeric") from exc
        if not np.isfinite(numeric) or numeric < 0.0:
            raise IOValidationError(
                f"accounting_tolerance.{name} must be finite and non-negative"
            )
        normalized[name] = numeric
    return normalized


__all__ = [
    "aggregate_sector_vector",
    "axis_sum",
    "inflow_adjustment",
    "input_adjustment_vector",
    "normalize_tolerance",
    "outflow_adjustment",
    "resolve_input_adjustment",
    "trade_side",
    "vector",
]
