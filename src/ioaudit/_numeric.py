"""Small, defensive numeric helpers shared by v0.2 system audits."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import sparse


def safe_vector_sum(value: Any, *, axis: int) -> np.ndarray | None:
    """Return a finite vector sum, or ``None`` for invalid derived values.

    The helper deliberately suppresses floating-point overflow warnings.  A
    finite input can produce an infinite reduction, which is a diagnostic
    outcome rather than a reason for the audit process itself to crash.
    """

    if value is None:
        return None
    try:
        with np.errstate(over="ignore", invalid="ignore"):
            if sparse.issparse(value):
                result = np.asarray(value.sum(axis=axis), dtype=float).reshape(-1)
            else:
                result = np.sum(np.asarray(value), axis=axis, dtype=float)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if np.isfinite(result).all() else None


def safe_vector_add(*values: np.ndarray | None) -> np.ndarray | None:
    """Add vectors and return ``None`` when any derived value is non-finite."""

    if not values or any(value is None for value in values):
        return None
    try:
        with np.errstate(over="ignore", invalid="ignore"):
            result = np.asarray(values[0], dtype=float).copy()
            for value in values[1:]:
                result = result + np.asarray(value, dtype=float)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if np.isfinite(result).all() else None


__all__ = ["safe_vector_add", "safe_vector_sum"]
