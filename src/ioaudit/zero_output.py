"""Diagnostics for sectors with zero output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .structure import _all_finite, _is_sparse, _shape_of


@dataclass
class ZeroOutputDiagnostics:
    """Describe zero-output columns without changing the source table."""

    status: str = "SKIPPED"
    zero_output_sectors: list[Any] = field(default_factory=list)
    zero_output_indices: list[int] = field(default_factory=list)
    consistent_sectors: list[Any] = field(default_factory=list)
    inconsistent_sectors: list[Any] = field(default_factory=list)
    consistent_zero_output: bool | None = None
    all_zero_rows: list[Any] = field(default_factory=list)
    all_zero_row_indices: list[int] = field(default_factory=list)
    all_zero_columns: list[Any] = field(default_factory=list)
    all_zero_column_indices: list[int] = field(default_factory=list)
    all_zero_rows_with_positive_output: list[Any] = field(default_factory=list)
    all_zero_columns_with_positive_output: list[Any] = field(default_factory=list)
    all_zero_rows_with_positive_final_demand: list[Any] = field(default_factory=list)
    all_zero_rows_without_final_demand_evidence: list[Any] = field(default_factory=list)
    all_zero_columns_with_positive_value_added: list[Any] = field(default_factory=list)
    all_zero_columns_without_value_added_evidence: list[Any] = field(default_factory=list)
    isolated_sectors: list[Any] = field(default_factory=list)
    isolated_indices: list[int] = field(default_factory=list)


def diagnose_zero_output(
    z: Any,
    x: np.ndarray | None,
    sectors: list[Any],
    *,
    final_demand: np.ndarray | None,
    value_added: np.ndarray | None,
) -> ZeroOutputDiagnostics:
    """Find zero-output and abnormal zero-structure sectors.

    Zero rows/columns are reported as evidence only.  They are not removed and
    are not automatically treated as failures; only a nonzero-output column
    with nonzero transactions is the existing logical inconsistency check.
    """

    result = ZeroOutputDiagnostics()
    z_shape = _shape_of(z) if z is not None else ()
    if z is None or x is None or len(z_shape) != 2 or getattr(x, "ndim", None) != 1 or len(x) != z_shape[1]:
        return result
    if not _all_finite(z) or not _all_finite(x):
        return result
    if _is_sparse(z):
        row_indices = [int(i) for i in range(z_shape[0]) if z.getrow(i).nnz == 0]
        column_indices = [int(i) for i in range(z_shape[1]) if z.getcol(i).nnz == 0]
    else:
        array = np.asarray(z, dtype=float)
        row_indices = [int(i) for i in np.flatnonzero(np.all(array == 0, axis=1))]
        column_indices = [int(i) for i in np.flatnonzero(np.all(array == 0, axis=0))]
    result.all_zero_row_indices = row_indices
    result.all_zero_column_indices = column_indices
    result.all_zero_rows = [sectors[i] if i < len(sectors) else i for i in row_indices]
    result.all_zero_columns = [sectors[i] if i < len(sectors) else i for i in column_indices]
    result.all_zero_rows_with_positive_output = [
        sectors[i] if i < len(sectors) else i for i in row_indices if i < len(x) and x[i] > 0
    ]
    result.all_zero_columns_with_positive_output = [
        sectors[i] if i < len(sectors) else i for i in column_indices if i < len(x) and x[i] > 0
    ]

    indices = [int(i) for i in np.flatnonzero(x == 0)]
    result.zero_output_indices = indices
    result.zero_output_sectors = [sectors[i] if i < len(sectors) else i for i in indices]
    for index in indices:
        sector = sectors[index] if index < len(sectors) else index
        if _is_sparse(z):
            is_zero_column = not np.any(z.getcol(index).data != 0)
        else:
            is_zero_column = bool(np.all(z[:, index] == 0))
        if is_zero_column:
            result.consistent_sectors.append(sector)
        else:
            result.inconsistent_sectors.append(sector)
    result.consistent_zero_output = not result.inconsistent_sectors
    result.status = "FAIL" if result.inconsistent_sectors else "PASS"

    if final_demand is None:
        result.all_zero_rows_without_final_demand_evidence = list(result.all_zero_rows)
    else:
        result.all_zero_rows_with_positive_final_demand = [
            sectors[i] if i < len(sectors) else i
            for i in row_indices
            if i < len(final_demand) and final_demand[i] > 0
        ]
        result.all_zero_rows_without_final_demand_evidence = [
            sectors[i] if i < len(sectors) else i
            for i in row_indices
            if i < len(final_demand) and final_demand[i] <= 0
        ]
    if value_added is None:
        result.all_zero_columns_without_value_added_evidence = list(result.all_zero_columns)
    else:
        result.all_zero_columns_with_positive_value_added = [
            sectors[i] if i < len(sectors) else i
            for i in column_indices
            if i < len(value_added) and value_added[i] > 0
        ]
        result.all_zero_columns_without_value_added_evidence = [
            sectors[i] if i < len(sectors) else i
            for i in column_indices
            if i < len(value_added) and value_added[i] <= 0
        ]
    if final_demand is not None and value_added is not None:
        for index in range(min(z_shape[0], z_shape[1], len(sectors))):
            if index in row_indices and index in column_indices and final_demand[index] == 0 and value_added[index] == 0:
                result.isolated_indices.append(index)
                result.isolated_sectors.append(sectors[index])
    return result
