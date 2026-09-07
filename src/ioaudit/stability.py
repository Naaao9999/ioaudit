"""Numerical diagnostics for the Leontief system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import warnings

import numpy as np
from scipy import sparse
from scipy.sparse import linalg as spla

from .structure import _all_finite, _is_sparse, _shape_of


@dataclass
class StabilityDiagnostics:
    """Results for ``B = I - A`` and its Leontief inverse."""

    status: str = "SKIPPED"
    invertible: bool | None = None
    spectral_radius: float | None = None
    spectral_radius_exact: bool | None = None
    condition_number: float | None = None
    condition_number_exact: bool | None = None
    leontief_inverse: Any = None
    leontief_inverse_finite: bool | None = None
    negative_inverse_entries: dict[str, Any] = field(
        default_factory=lambda: {"count": 0, "locations": [], "values": []}
    )
    column_multipliers: list[float] | None = None
    B: Any = None
    reason: str | None = None

    @property
    def L_calculated(self) -> Any:
        """Alias for the calculated Leontief inverse."""

        return self.leontief_inverse


def _dense_spectral_radius(a: np.ndarray) -> float:
    values = np.linalg.eigvals(a)
    return float(np.max(np.abs(values))) if values.size else 0.0


def _small_sparse_spectral_radius(a: Any) -> float:
    """Compute a 1x1/2x2 sparse eigenvalue problem without densifying it."""

    n = a.shape[0]
    if n == 0:
        return 0.0
    if n == 1:
        return float(abs(a[0, 0]))
    aa = float(a[0, 0])
    bb = float(a[0, 1])
    cc = float(a[1, 0])
    dd = float(a[1, 1])
    values = np.linalg.eigvals(np.array([[aa, bb], [cc, dd]], dtype=float))
    return float(np.max(np.abs(values)))


def _iterative_spectral_radius(a: Any) -> tuple[float | None, bool]:
    n = a.shape[0]
    if n <= 2:
        if _is_sparse(a):
            return _small_sparse_spectral_radius(a), True
        return _dense_spectral_radius(np.asarray(a, dtype=float)), True
    try:
        matrix = a if _is_sparse(a) else sparse.csr_matrix(a)
        matrix = matrix.tocsr().astype(float, copy=True)
        scale = float(np.max(np.abs(matrix.data))) if matrix.nnz else 0.0
        if scale == 0.0:
            return 0.0, False
        # After rescaling, ARPACK's absolute eigenvalue error is rescaled by
        # the same factor.  Once one machine epsilon in the normalized solve
        # exceeds one unit in the original scale, a finite estimate can be
        # materially misleading, so report it as unavailable.
        if np.finfo(float).eps * scale > 1.0:
            return None, False
        # ARPACK first normalizes internally, but doing this explicitly avoids
        # overflow in its norm calculations for finite matrices with very
        # large IO values.  Eigenvalues are restored after the solve.
        values = spla.eigs(
            matrix / scale,
            k=1,
            which="LM",
            return_eigenvectors=False,
        )
        spectral_radius = float(np.max(np.abs(values))) * scale
        if not np.isfinite(spectral_radius):
            return None, False
        return spectral_radius, False
    except Exception:
        # Power iteration is not a reliable spectral-radius algorithm for a
        # general IO coefficient matrix: it can converge to a singular value
        # and silently under-estimate rho.  Report the estimate as unavailable
        # so threshold checks cannot treat an unsafe fallback as a pass.
        return None, False


def _negative_entries(matrix: np.ndarray) -> dict[str, Any]:
    indices = np.argwhere(np.isfinite(matrix) & (matrix < 0))
    return {
        "count": int(len(indices)),
        "locations": [list(map(int, index)) for index in indices],
        "values": [float(matrix[tuple(index)]) for index in indices],
    }


def _iterative_condition_and_solve(
    b: Any,
) -> tuple[bool, float | None, np.ndarray | None, str | None, bool | None]:
    """Factor ``B`` and estimate its condition independently.

    A failed condition estimate is not evidence that the matrix is singular;
    sparse factorization and the multiplier solve are the invertibility test.
    """

    b_sparse = b.tocsc() if _is_sparse(b) else sparse.csc_matrix(b)
    try:
        lu = spla.splu(b_sparse)
    except Exception as exc:
        return False, None, None, f"sparse factorization of I - A failed: {exc}", None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            multipliers = np.asarray(
                lu.solve(np.ones(b_sparse.shape[0]), "T"), dtype=float
            )
    except Exception as exc:
        return False, None, None, f"multiplier solve failed: {exc}", None
    if not np.isfinite(multipliers).all():
        return (
            True,
            None,
            None,
            "multiplier solve produced non-finite values",
            False,
        )

    try:
        norm_b = float(np.max(np.asarray(np.abs(b_sparse).sum(axis=0)).reshape(-1)))
        operator = spla.LinearOperator(
            b_sparse.shape,
            matvec=lambda vector: lu.solve(vector),
            rmatvec=lambda vector: lu.solve(vector, "T"),
            dtype=float,
        )
        estimate = norm_b * float(spla.onenormest(operator))
        if not np.isfinite(estimate):
            raise FloatingPointError("condition estimate is non-finite")
        condition_reason = None
    except Exception as exc:
        estimate = None
        condition_reason = f"condition number estimate unavailable: {exc}"
    return True, estimate, multipliers, condition_reason, True


def diagnose_stability(a: Any, numerical_method: str = "dense") -> StabilityDiagnostics:
    """Diagnose invertibility and stability without unconditional large SVDs."""

    result = StabilityDiagnostics()
    a_shape = _shape_of(a) if a is not None else ()
    if a is None or len(a_shape) != 2 or a_shape[0] != a_shape[1]:
        result.reason = "requires a square coefficient matrix"
        return result
    if not _all_finite(a):
        result.reason = "coefficient matrix contains NaN/Inf"
        return result
    n = a_shape[0]
    try:
        if numerical_method == "dense":
            a_dense = np.asarray(a.toarray() if _is_sparse(a) else a, dtype=float)
            b = np.eye(n, dtype=float) - a_dense
            result.B = b
            result.spectral_radius = _dense_spectral_radius(a_dense)
            result.spectral_radius_exact = True
            try:
                result.condition_number = float(np.linalg.cond(b))
                result.condition_number_exact = True
            except np.linalg.LinAlgError:
                result.condition_number = float("inf")
                result.condition_number_exact = True
            try:
                inverse = np.linalg.inv(b)
                result.invertible = True
                result.leontief_inverse = inverse
                result.leontief_inverse_finite = bool(np.isfinite(inverse).all())
                result.negative_inverse_entries = _negative_entries(inverse)
                result.column_multipliers = inverse.sum(axis=0).tolist()
            except np.linalg.LinAlgError:
                result.invertible = False
                result.leontief_inverse_finite = False
                result.reason = "I - A is singular"
        elif numerical_method == "iterative":
            a_sparse = a if _is_sparse(a) else sparse.csr_matrix(a)
            b = sparse.eye(n, format="csc") - a_sparse.tocsc()
            result.B = b
            result.spectral_radius, result.spectral_radius_exact = _iterative_spectral_radius(a_sparse)
            (
                invertible,
                estimate,
                multipliers,
                condition_reason,
                multipliers_finite,
            ) = _iterative_condition_and_solve(b)
            result.invertible = invertible
            result.condition_number = estimate
            result.condition_number_exact = False if estimate is not None else None
            result.column_multipliers = multipliers.tolist() if multipliers is not None else None
            reasons: list[str] = []
            if result.spectral_radius is None:
                reasons.append("spectral radius estimate unavailable")
            if condition_reason:
                reasons.append(condition_reason)
            if invertible:
                result.leontief_inverse_finite = (
                    False if multipliers_finite is False else None
                )
                result.negative_inverse_entries = {
                    "available": False,
                    "count": None,
                    "locations": [],
                    "values": [],
                }
                if multipliers_finite is not False:
                    reasons.append(
                        "inverse finiteness and negative entries were not materialized on iterative route"
                    )
            else:
                result.leontief_inverse_finite = False
                reasons.append("sparse factorization of I - A failed")
            result.reason = "; ".join(reasons)
        else:
            result.reason = f"unknown numerical method: {numerical_method}"
            return result
    except Exception as exc:
        result.reason = f"stability calculation failed: {exc}"
        result.invertible = None
        result.leontief_inverse_finite = None
        return result
    result.status = (
        "PASS"
        if result.invertible and result.leontief_inverse_finite is not False
        else "FAIL"
    )
    return result
