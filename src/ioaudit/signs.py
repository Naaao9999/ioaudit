"""Detection of negative signed entries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .structure import _as_array, _is_sparse, _labels


@dataclass
class NegativeEntries:
    """Locations and values of negative entries in one input field."""

    count: int = 0
    locations: list[dict[str, Any]] = field(default_factory=list)
    values: list[float] = field(default_factory=list)


@dataclass
class SignDiagnostics:
    """Negative-entry diagnostics; negative values are informational."""

    status: str = "PASS"
    negative_transaction_cells: NegativeEntries = field(default_factory=NegativeEntries)
    negative_final_demand: NegativeEntries = field(default_factory=NegativeEntries)
    negative_value_added: NegativeEntries = field(default_factory=NegativeEntries)
    negative_imports: NegativeEntries = field(default_factory=NegativeEntries)
    negative_exports: NegativeEntries = field(default_factory=NegativeEntries)
    total_negative_entries: int = 0


def _negative(value: Any, name: str, row_labels: list[Any] | None = None, col_labels: list[Any] | None = None) -> NegativeEntries:
    result = NegativeEntries()
    if value is None:
        return result
    try:
        if _is_sparse(value):
            coo = value.tocoo()
            entries = [
                (int(row), int(column), float(item))
                for row, column, item in zip(coo.row, coo.col, np.asarray(coo.data))
                if np.isfinite(item) and item < 0
            ]
        else:
            array = _as_array(value).astype(float)
            entries = [
                (tuple(int(i) for i in index), float(array[tuple(index)]))
                for index in np.argwhere(np.isfinite(array) & (array < 0))
            ]
    except (TypeError, ValueError):
        return result
    for entry in entries:
        if _is_sparse(value):
            idx = (entry[0], entry[1])
            number = entry[2]
        else:
            idx, number = entry
        location: dict[str, Any] = {"field": name, "index": list(idx)}
        if len(idx) == 1:
            if row_labels is not None and idx[0] < len(row_labels):
                location["row_label"] = row_labels[idx[0]]
        elif len(idx) >= 2:
            if row_labels is not None and idx[0] < len(row_labels):
                location["row_label"] = row_labels[idx[0]]
            if col_labels is not None and idx[1] < len(col_labels):
                location["column_label"] = col_labels[idx[1]]
        result.locations.append(location)
        result.values.append(float(number))
    result.count = len(result.values)
    return result


def _merge_entries(target: NegativeEntries, source: NegativeEntries) -> None:
    """Append one field's negative-entry evidence to a side diagnostic."""

    target.count += source.count
    target.locations.extend(source.locations)
    target.values.extend(source.values)


def _trade_negative_entries(
    trade: Any,
    names: tuple[str, ...],
    labels: list[Any] | None,
) -> NegativeEntries:
    result = NegativeEntries()
    if trade is None:
        return result
    for field_name in names:
        value = getattr(trade, field_name, None)
        if value is not None:
            _merge_entries(result, _negative(value, f"trade.{field_name}", labels))
    return result


def diagnose_signs(io: Any) -> SignDiagnostics:
    """Find negative values without assigning a quality judgment."""

    z_index, z_columns = _labels(io.Z)
    y_index, _ = _labels(io.Y)
    y_index = y_index if y_index is not None else z_index
    v_index, v_columns = _labels(io.V)
    trade = getattr(io, "trade", None)
    if trade is not None:
        negative_imports = _trade_negative_entries(
            trade,
            ("interregional_inflows", "international_imports", "combined_inflows"),
            z_index,
        )
        negative_exports = _trade_negative_entries(
            trade,
            ("interregional_outflows", "international_exports", "combined_outflows"),
            z_index,
        )
    else:
        negative_imports = _negative(getattr(io, "imports", None), "imports", z_index)
        negative_exports = _negative(getattr(io, "exports", None), "exports", z_index)
    result = SignDiagnostics(
        negative_transaction_cells=_negative(io.Z, "Z", z_index, z_columns),
        negative_final_demand=_negative(io.Y, "Y", y_index),
        negative_value_added=_negative(io.V, "V", v_index, v_columns),
        negative_imports=negative_imports,
        negative_exports=negative_exports,
    )
    result.total_negative_entries = sum(
        item.count
        for item in (
            result.negative_transaction_cells,
            result.negative_final_demand,
            result.negative_value_added,
            result.negative_imports,
            result.negative_exports,
        )
    )
    return result
