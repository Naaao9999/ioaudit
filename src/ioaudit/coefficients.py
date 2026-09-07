"""Technical-coefficient diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .structure import _all_finite, _is_sparse, _shape_of


@dataclass
class CoefficientDiagnostics:
    """Safe technical coefficients ``A = Z / x`` by column."""

    status: str = "SKIPPED"
    A: Any = None
    finite_coefficients: bool | None = None
    column_sums: list[float] = field(default_factory=list)
    negative_coefficients: dict[str, Any] = field(
        default_factory=lambda: {"count": 0, "locations": [], "values": []}
    )
    self_input_coefficients: list[float] = field(default_factory=list)
    zero_output_mask: list[bool] = field(default_factory=list)
    distribution: dict[str, float | int | None] = field(default_factory=dict)
    reason: str | None = None

    @property
    def A_calculated(self) -> Any:
        """Alias used when comparing the result with a reference matrix."""

        return self.A


def _empty_distribution() -> dict[str, float | int | None]:
    return {
        "count": 0,
        "min": None,
        "max": None,
        "mean": None,
        "std": None,
        "median": None,
        "p01": None,
        "p99": None,
    }


def _dense_distribution(values: np.ndarray) -> dict[str, float | int | None]:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return _empty_distribution()
    return {
        "count": int(finite.size),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "median": float(np.median(finite)),
        "p01": float(np.quantile(finite, 0.01)),
        "p99": float(np.quantile(finite, 0.99)),
    }


def _sparse_quantile(nonzero: np.ndarray, total: int, q: float) -> float:
    """Return an exact quantile for sparse values plus implicit zeros."""

    if total == 0:
        return float("nan")
    values = np.sort(np.asarray(nonzero, dtype=float))
    zero_count = total - len(values)
    negative_count = int(np.searchsorted(values, 0.0, side="left"))
    rank = q * (total - 1)

    def at(index: int) -> float:
        if index < negative_count:
            return float(values[index])
        if index < negative_count + zero_count:
            return 0.0
        return float(values[index - zero_count])

    lower = at(int(np.floor(rank)))
    upper = at(int(np.ceil(rank)))
    return lower + (upper - lower) * (rank - np.floor(rank))


def _sparse_distribution(matrix: Any) -> dict[str, float | int | None]:
    shape = _shape_of(matrix)
    total = int(np.prod(shape, dtype=np.int64))
    data = np.asarray(matrix.data, dtype=float)
    nonzero = data[data != 0]
    if total == 0:
        return _empty_distribution()
    total_sum = float(np.sum(data))
    total_sq = float(np.sum(data * data))
    mean = total_sum / total
    variance = max(0.0, total_sq / total - mean * mean)
    minimum = min(0.0, float(np.min(nonzero))) if nonzero.size else 0.0
    maximum = max(0.0, float(np.max(nonzero))) if nonzero.size else 0.0
    return {
        "count": total,
        "min": minimum,
        "max": maximum,
        "mean": mean,
        "std": float(np.sqrt(variance)),
        "median": _sparse_quantile(nonzero, total, 0.5),
        "p01": _sparse_quantile(nonzero, total, 0.01),
        "p99": _sparse_quantile(nonzero, total, 0.99),
    }


def _negative_entries(matrix: Any) -> dict[str, Any]:
    if _is_sparse(matrix):
        coo = matrix.tocoo()
        entries = [
            (int(row), int(column), float(value))
            for row, column, value in zip(coo.row, coo.col, np.asarray(coo.data))
            if np.isfinite(value) and value < 0
        ]
    else:
        array = np.asarray(matrix, dtype=float)
        entries = [
            (int(index[0]), int(index[1]), float(array[tuple(index)]))
            for index in np.argwhere(np.isfinite(array) & (array < 0))
        ]
    return {
        "count": len(entries),
        "locations": [[row, column] for row, column, _ in entries],
        "values": [value for _, _, value in entries],
    }


def diagnose_coefficients(z: Any, x: np.ndarray | None) -> CoefficientDiagnostics:
    """Construct finite coefficients without allowing zero-output leakage.

    A zero-output column with a zero transaction column is represented by a
    zero coefficient column.  A zero-output column with nonzero transactions
    is logically inconsistent, so coefficient and Leontief calculations are
    SKIPPED rather than made to look solvable by silently zeroing it.
    """

    result = CoefficientDiagnostics()
    z_shape = _shape_of(z) if z is not None else ()
    if x is not None and getattr(x, "ndim", None) == 1:
        result.zero_output_mask = (x == 0).tolist()
    if z is None or x is None or len(z_shape) != 2 or z_shape[0] != z_shape[1] or getattr(x, "ndim", None) != 1 or len(x) != z_shape[1]:
        result.reason = "requires numeric square Z and aligned x"
        return result
    if not _all_finite(z) or not _all_finite(x):
        result.reason = "Z or x contains NaN/Inf"
        return result
    zero_columns = np.flatnonzero(x == 0)
    inconsistent = [
        int(index)
        for index in zero_columns
        if (
            np.any(z.getcol(int(index)).data != 0)
            if _is_sparse(z)
            else np.any(z[:, int(index)] != 0)
        )
    ]
    if inconsistent:
        result.reason = (
            "inconsistent zero-output columns contain nonzero transactions: "
            + ", ".join(str(index) for index in inconsistent)
        )
        return result
    try:
        x_array = np.asarray(x, dtype=float)
        inverse_x = np.divide(
            1.0,
            x_array,
            out=np.zeros(len(x_array), dtype=float),
            where=x_array != 0,
        )
        if _is_sparse(z):
            a = z.multiply(inverse_x).tocsr()
        else:
            a = np.zeros(z_shape, dtype=float)
            np.divide(z, x_array[np.newaxis, :], out=a, where=x_array[np.newaxis, :] != 0)
    except (TypeError, ValueError, FloatingPointError) as exc:
        result.reason = f"coefficient calculation failed: {exc}"
        return result
    result.A = a
    result.finite_coefficients = _all_finite(a)
    result.status = "PASS" if result.finite_coefficients else "FAIL"
    result.column_sums = np.asarray(a.sum(axis=0), dtype=float).reshape(-1).tolist()
    result.self_input_coefficients = np.asarray(a.diagonal(), dtype=float).reshape(-1).tolist()
    result.negative_coefficients = _negative_entries(a)
    result.distribution = _sparse_distribution(a) if _is_sparse(a) else _dense_distribution(np.asarray(a))
    if not result.finite_coefficients:
        result.reason = "calculated coefficients contain NaN/Inf"
    return result
