"""Resolution of output-adjustment component roles.

This module keeps the semantic overlap checks for ``output_adjustments``
outside the accounting-plan compiler.  The compiler consumes the resolved
result and remains responsible for assembling accounting equations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .structure import _normalize_label, _shape_of


OUTPUT_ADJUSTMENT_ROLES = frozenset({"inflow", "outflow", "other"})

OUTPUT_TRADE_LABELS = frozenset(
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


def component_labels(value: Any) -> list[Any] | None:
    """Return component labels for a two-dimensional adjustment block."""

    if value is None:
        return None
    columns = getattr(value, "columns", None)
    if columns is None:
        return None
    labels = list(columns)
    return labels or None


def resolve_roles(
    value: Any,
    roles: Any,
) -> tuple[tuple[str, ...] | None, str | None]:
    """Resolve an explicit role declaration for adjustment components."""

    if roles is None:
        return None, None
    try:
        shape = _shape_of(value)
    except Exception as exc:
        return None, f"output_adjustment_roles could not read adjustment shape: {exc}"
    if len(shape) != 2:
        return (
            None,
            "output_adjustment_roles apply only to two-dimensional "
            "output_adjustments",
        )
    component_count = shape[1]
    if isinstance(roles, Mapping):
        labels = component_labels(value)
        if labels is None or len(labels) != component_count:
            return (
                None,
                "mapping output_adjustment_roles require DataFrame component labels",
            )
        normalized_keys: dict[str, list[Any]] = {}
        for key in roles:
            normalized_keys.setdefault(_normalize_label(key), []).append(key)
        resolved: list[str] = []
        for label in labels:
            matching_keys: list[Any] = []
            try:
                if label in roles:
                    matching_keys = [label]
            except TypeError:
                matching_keys = []
            if not matching_keys:
                matching_keys = normalized_keys.get(_normalize_label(label), [])
            if len(matching_keys) != 1:
                return (
                    None,
                    "output_adjustment_roles do not provide one unambiguous role "
                    f"for component {label!r}",
                )
            resolved.append(roles[matching_keys[0]])
    elif isinstance(roles, Sequence) and not isinstance(roles, (str, bytes)):
        resolved = list(roles)
        if len(resolved) != component_count:
            return (
                None,
                "output_adjustment_roles must contain one role per adjustment component",
            )
    else:
        return (
            None,
            "output_adjustment_roles must be a mapping or a one-dimensional sequence",
        )

    if any(
        not isinstance(role, str) or role not in OUTPUT_ADJUSTMENT_ROLES
        for role in resolved
    ):
        return (
            None,
            "output_adjustment_roles must use only 'inflow', 'outflow', or 'other'",
        )
    return tuple(resolved), None


def trade_conflict(
    io: Any,
    value: Any,
    *,
    roles: Any = None,
) -> str | None:
    """Reject ambiguous overlap between output adjustments and trade flows."""

    trade = getattr(io, "trade", None)
    if trade is None or not trade.has_any or value is None:
        return None
    resolved_roles, roles_reason = resolve_roles(value, roles)
    if roles_reason:
        return roles_reason
    try:
        shape = _shape_of(value)
    except Exception:
        shape = ()
    if len(shape) != 2:
        return (
            "output_adjustments were supplied with TradeFlows but their "
            "component roles are unavailable; possible trade double-counting "
            "cannot be ruled out"
        )
    if resolved_roles is None:
        labels = component_labels(value)
        if labels:
            normalized = {_normalize_label(label) for label in labels}
            overlaps = sorted(normalized & OUTPUT_TRADE_LABELS)
            if overlaps:
                return (
                    "output_adjustments overlap with declared trade component(s): "
                    + ", ".join(overlaps)
                )
        return (
            "output_adjustment_roles must explicitly classify every two-dimensional "
            "output_adjustments component when TradeFlows are supplied"
        )
    if any(role in {"inflow", "outflow"} for role in resolved_roles):
        return (
            "output_adjustment_roles declares trade-related components; "
            "use either TradeFlows or output_adjustments for those flows, not both"
        )
    return None


__all__ = [
    "OUTPUT_ADJUSTMENT_ROLES",
    "OUTPUT_TRADE_LABELS",
    "component_labels",
    "resolve_roles",
    "trade_conflict",
]
