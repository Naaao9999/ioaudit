"""v0.2 data models and audits for SUT and MRIO tables.

The v0.1 :class:`~ioaudit.IOSystem` remains the model for one symmetric
input-output table.  This module keeps supply-use tables and multi-region
tables separate so that their axes and accounting identities stay explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
from collections.abc import Mapping
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from .audit import _select_method
from .coefficients import diagnose_coefficients
from .exceptions import IOValidationError
from .metadata import diagnose_metadata
from .model import _copy_value
from .provenance import _canonical
from .reference import diagnose_reference
from .results import SystemAuditReport
from .stability import diagnose_stability
from .structure import _all_finite, _as_array, _is_sparse, _shape_of, _numeric_array
from ._version import __version__


@dataclass
class V02BalanceCheck:
    """Residuals for one SUT or MRIO accounting identity."""

    status: str = "SKIPPED"
    equation: str = ""
    residual: list[float] = field(default_factory=list)
    absolute_residual: list[float] = field(default_factory=list)
    relative_residual: list[float] = field(default_factory=list)
    mae: float | None = None
    rmse: float | None = None
    max_absolute_residual: float | None = None
    max_relative_residual: float | None = None
    residual_class: str | None = None
    reason: str | None = None


@dataclass
class SUTStructureDiagnostics:
    """Structural checks for a supply-use table."""

    status: str = "SKIPPED"
    n_products: int = 0
    n_industries: int = 0
    fields: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SUTAccountingDiagnostics:
    """Supply-use accounting checks, kept separate from SIOT accounting."""

    status: str = "SKIPPED"
    commodity_balance: V02BalanceCheck = field(default_factory=V02BalanceCheck)
    industry_balance: V02BalanceCheck = field(default_factory=V02BalanceCheck)
    make_product_balance: V02BalanceCheck = field(default_factory=V02BalanceCheck)
    make_industry_balance: V02BalanceCheck = field(default_factory=V02BalanceCheck)
    notes: list[str] = field(default_factory=list)

    @property
    def output_balance(self) -> V02BalanceCheck:
        """Alias for the commodity/output balance."""

        return self.commodity_balance

    @property
    def input_balance(self) -> V02BalanceCheck:
        """Alias for the industry/input balance."""

        return self.industry_balance

    @property
    def max_relative_residual(self) -> float | None:
        """Maximum relative residual across the available SUT identities."""

        values = [
            check.max_relative_residual
            for check in (
                self.commodity_balance,
                self.industry_balance,
                self.make_product_balance,
                self.make_industry_balance,
            )
            if check.max_relative_residual is not None
        ]
        return max(values) if values else None


@dataclass
class MRIOStructureDiagnostics:
    """Structural checks for a region-by-sector matrix."""

    status: str = "SKIPPED"
    supporting_status: str = "SKIPPED"
    n_regions: int = 0
    n_sectors: int = 0
    n_total: int = 0
    expected_labels: list[tuple[Any, Any]] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)
    block_structure: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    supporting_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class MRIOAccountingDiagnostics:
    """Total embedded-flow identities for an expanded MRIO table."""

    status: str = "SKIPPED"
    output_balance: V02BalanceCheck = field(default_factory=V02BalanceCheck)
    input_balance: V02BalanceCheck = field(default_factory=V02BalanceCheck)
    notes: list[str] = field(default_factory=list)

    @property
    def max_relative_residual(self) -> float | None:
        """Maximum relative residual across the two total identities."""

        values = [
            check.max_relative_residual
            for check in (self.input_balance, self.output_balance)
            if check.max_relative_residual is not None
        ]
        return max(values) if values else None


class SUTSystem:
    """Container for an explicit supply-use table.

    ``use`` is a product-by-industry intermediate-use matrix.  ``make`` and
    ``supply`` are optional product-by-industry matrices.  Final demand is
    product-by-category, value added is industry-based, and the two output
    vectors are kept separate.  No SUT-to-SIOT transformation is performed.
    """

    def __init__(
        self,
        *,
        use: Any,
        products: Sequence[Any],
        industries: Sequence[Any],
        make: Any = None,
        supply: Any = None,
        final_demand: Any = None,
        output_by_industry: Any = None,
        output_by_product: Any = None,
        output_by_product_scope: str = "unknown",
        value_added: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if use is None:
            raise IOValidationError("use is required")
        try:
            self.products = list(products)
            self.industries = list(industries)
        except Exception as exc:
            raise IOValidationError("products and industries must be sequences") from exc
        if not isinstance(output_by_product_scope, str) or output_by_product_scope not in {
            "domestic_output",
            "total_supply",
            "unknown",
        }:
            raise IOValidationError(
                "output_by_product_scope must be 'domestic_output', "
                "'total_supply', or 'unknown'"
            )
        self.use = _copy_value(use, "use", allow_none=False)
        self.make = _copy_value(make, "make")
        self.supply = _copy_value(supply, "supply")
        self.final_demand = _copy_value(final_demand, "final_demand")
        self.output_by_industry = _copy_value(output_by_industry, "output_by_industry")
        self.output_by_product = _copy_value(output_by_product, "output_by_product")
        self.output_by_product_scope = output_by_product_scope
        self.value_added = _copy_value(value_added, "value_added")
        if metadata is None:
            self.metadata = {}
        elif isinstance(metadata, Mapping):
            self.metadata = dict(metadata)
        else:
            raise IOValidationError("metadata must be a mapping")


class MRIOSystem:
    """Container for an MRIO expanded to a region-by-sector square matrix.

    The canonical order is ``[(region, sector) for region in regions for
    sector in sectors]``.  ``Z`` and all labelled supporting arrays must use
    this order.  Bilateral trade-flow tensors and SUT transformations are
    outside this first v0.2 model.
    """

    def __init__(
        self,
        *,
        Z: Any,
        x: Any,
        regions: Sequence[Any],
        sectors: Sequence[Any],
        Y: Any = None,
        V: Any = None,
        A_reference: Any = None,
        L_reference: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if Z is None or x is None:
            raise IOValidationError("Z and x are required")
        try:
            self.regions = list(regions)
            self.sectors = list(sectors)
        except Exception as exc:
            raise IOValidationError("regions and sectors must be sequences") from exc
        self.Z = _copy_value(Z, "Z", allow_none=False)
        self.x = _copy_value(x, "x", allow_none=False)
        self.Y = _copy_value(Y, "Y")
        self.V = _copy_value(V, "V")
        self.A_reference = _copy_value(A_reference, "A_reference")
        self.L_reference = _copy_value(L_reference, "L_reference")
        if metadata is None:
            self.metadata = {}
        elif isinstance(metadata, Mapping):
            self.metadata = dict(metadata)
        else:
            raise IOValidationError("metadata must be a mapping")

    @property
    def labels(self) -> list[tuple[Any, Any]]:
        """Return the canonical region-sector labels."""

        return [(region, sector) for region in self.regions for sector in self.sectors]


def _field_labels(value: Any) -> tuple[list[Any] | None, list[Any] | None]:
    if isinstance(value, pd.DataFrame):
        return value.index.tolist(), value.columns.tolist()
    if isinstance(value, pd.Series):
        return value.index.tolist(), None
    return None, None


def _same_labels(actual: list[Any] | None, expected: Sequence[Any]) -> bool | None:
    if actual is None:
        return None
    return len(actual) == len(expected) and all(a == b for a, b in zip(actual, expected))


def _validate_value(
    value: Any,
    *,
    expected_shapes: set[tuple[int, ...]] | None = None,
    shape_validator: Callable[[tuple[int, ...]], bool] | None = None,
    row_labels: Sequence[Any] | None = None,
    column_labels: Sequence[Any] | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Read a field without mutating it and return diagnostics metadata."""

    details: dict[str, Any] = {"status": "PASS"}
    if value is None:
        details.update(status="SKIPPED", reason="not supplied")
        return None, details
    try:
        shape = _shape_of(value)
    except Exception as exc:
        details.update(status="FAIL", reason=f"shape could not be read: {exc}")
        return None, details
    details["shape"] = list(shape)
    valid_shape = (
        shape in expected_shapes if expected_shapes is not None else shape_validator(shape)
    )
    if not valid_shape:
        details.update(
            status="FAIL",
            reason=(
                f"shape {shape} is not one of {sorted(expected_shapes)}"
                if expected_shapes is not None
                else f"shape {shape} does not satisfy the expected axis dimensions"
            ),
        )
        return None, details
    try:
        numeric, bad = _numeric_array(value)
    except Exception as exc:
        details.update(status="FAIL", reason=f"numeric conversion failed: {exc}")
        return None, details
    if numeric is None or bad:
        details.update(
            status="FAIL",
            reason="contains non-numeric or missing values",
            non_numeric_locations=[list(index) for index in bad[:20]],
        )
        return None, details
    try:
        if _is_sparse(numeric):
            array = numeric.astype(float, copy=True)
        else:
            array = _as_array(numeric).astype(float, copy=False)
    except Exception as exc:
        details.update(status="FAIL", reason=f"numeric conversion failed: {exc}")
        return None, details
    if not _all_finite(array):
        details.update(status="FAIL", reason="contains NaN or Inf")
        return None, details
    actual_rows, actual_columns = _field_labels(value)
    if row_labels is not None:
        match = _same_labels(actual_rows, row_labels)
        details["row_labels_match"] = match
        if match is False:
            details.update(status="FAIL", reason="row labels do not match expected labels")
    if column_labels is not None:
        match = _same_labels(actual_columns, column_labels)
        details["column_labels_match"] = match
        if match is False:
            details.update(status="FAIL", reason="column labels do not match expected labels")
    return (array if details["status"] == "PASS" else None), details


def _vector_sum(array: np.ndarray, axis: int) -> np.ndarray | None:
    with np.errstate(over="ignore", invalid="ignore"):
        if _is_sparse(array):
            result = np.asarray(array.sum(axis=axis), dtype=float).reshape(-1)
        else:
            result = np.sum(array, axis=axis, dtype=float)
    return result if np.isfinite(result).all() else None


def _safe_vector_add(*values: np.ndarray | None) -> np.ndarray | None:
    """Add derived vectors and return ``None`` when the result is non-finite."""

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


def _check_balance(
    actual: np.ndarray | None,
    expected: np.ndarray | None,
    *,
    equation: str,
    tolerance: dict[str, float] | None,
) -> V02BalanceCheck:
    result = V02BalanceCheck(equation=equation)
    if actual is None or expected is None:
        result.reason = "required SUT/MRIO blocks are unavailable or invalid"
        return result
    try:
        actual_array = np.asarray(actual, dtype=float).reshape(-1)
        expected_array = np.asarray(expected, dtype=float).reshape(-1)
        with np.errstate(over="ignore", invalid="ignore"):
            residual = actual_array - expected_array
        absolute = np.abs(residual)
        relative = np.zeros_like(absolute)
        denominator = np.abs(expected_array)
        np.divide(absolute, denominator, out=relative, where=denominator != 0)
        relative[(denominator == 0) & (absolute != 0)] = np.inf
    except Exception as exc:
        result.reason = f"residual calculation failed: {exc}"
        return result
    if not np.isfinite(residual).all():
        result.status = "FAIL"
        result.reason = "derived accounting residual contains NaN or Inf"
        return result
    result.residual = residual.tolist()
    result.absolute_residual = absolute.tolist()
    result.relative_residual = relative.tolist()
    result.mae = float(np.mean(absolute)) if absolute.size else 0.0
    result.rmse = float(np.sqrt(np.mean(residual**2))) if residual.size else 0.0
    result.max_absolute_residual = float(np.max(absolute)) if absolute.size else 0.0
    result.max_relative_residual = float(np.max(relative)) if relative.size else 0.0
    exact = bool(
        np.all(absolute <= np.finfo(float).eps * np.maximum(1.0, np.abs(expected_array)))
    )
    if tolerance is None:
        result.status = "PASS" if exact else "AVAILABLE"
        result.residual_class = "exact" if exact else "nonzero"
        return result
    absolute_limit = float(tolerance.get("absolute", 0.0))
    relative_limit = float(tolerance.get("relative", 0.0))
    rounding_unit = float(tolerance.get("rounding_unit", 0.0))
    allowed = np.maximum.reduce(
        [
            np.full_like(absolute, absolute_limit),
            relative_limit * np.abs(expected_array),
            np.full_like(absolute, rounding_unit),
        ]
    )
    within = bool(np.all(absolute <= allowed))
    result.status = "PASS" if within else "FAIL"
    result.residual_class = "exact" if exact else ("rounding_level" if within else "outside_tolerance")
    return result


def _report_provenance(system: Any, system_type: str, tolerance: dict[str, float] | None) -> dict[str, Any]:
    payload = {name: getattr(system, name, None) for name in vars(system)}
    encoded = json.dumps(_canonical(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "ioaudit_version": __version__,
        "system_type": system_type,
        "input_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "accounting_tolerance": _canonical(tolerance),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _final_status(checks: Sequence[V02BalanceCheck]) -> str:
    available = [check for check in checks if check.status != "SKIPPED"]
    if not available:
        return "SKIPPED"
    if any(check.status == "FAIL" for check in available):
        return "FAIL"
    if any(check.status == "AVAILABLE" for check in available):
        return "AVAILABLE"
    return "PASS"


def audit_sut(
    sut: SUTSystem,
    *,
    accounting_tolerance: dict[str, float] | None = None,
) -> SystemAuditReport:
    """Audit an explicit SUT without converting it to an SIOT."""

    if not isinstance(sut, SUTSystem):
        raise IOValidationError("audit_sut expects a SUTSystem instance")
    p, i = len(sut.products), len(sut.industries)
    structure = SUTStructureDiagnostics(n_products=p, n_industries=i)
    if p == 0 or i == 0:
        structure.errors.append("products and industries must both be non-empty")
    if len(set(map(str, sut.products))) != p:
        structure.errors.append("duplicate product labels")
    if len(set(map(str, sut.industries))) != i:
        structure.errors.append("duplicate industry labels")
    use, structure.fields["use"] = _validate_value(
        sut.use,
        expected_shapes={(p, i)},
        row_labels=sut.products,
        column_labels=sut.industries,
    )
    if use is None:
        structure.errors.append("use is unavailable or structurally invalid")
    make, structure.fields["make"] = _validate_value(
        sut.make,
        expected_shapes={(p, i)},
        row_labels=sut.products,
        column_labels=sut.industries,
    )
    supply, structure.fields["supply"] = _validate_value(
        sut.supply,
        expected_shapes={(p, i)},
        row_labels=sut.products,
        column_labels=sut.industries,
    )
    final_demand, structure.fields["final_demand"] = _validate_value(
        sut.final_demand,
        shape_validator=lambda shape: len(shape) == 1 and shape == (p,)
        or len(shape) == 2 and shape[0] == p,
        row_labels=sut.products,
    )
    value_added, structure.fields["value_added"] = _validate_value(
        sut.value_added,
        shape_validator=lambda shape: len(shape) == 1 and shape == (i,)
        or len(shape) == 2 and shape[1] == i,
        column_labels=sut.industries,
    )
    output_i, structure.fields["output_by_industry"] = _validate_value(
        sut.output_by_industry,
        expected_shapes={(i,)},
        row_labels=sut.industries,
    )
    output_p, structure.fields["output_by_product"] = _validate_value(
        sut.output_by_product,
        expected_shapes={(p,)},
        row_labels=sut.products,
    )
    supplied_fields = {
        "make": make,
        "supply": supply,
        "final_demand": final_demand,
        "value_added": value_added,
        "output_by_industry": output_i,
        "output_by_product": output_p,
    }
    for name, info in structure.fields.items():
        if info.get("status") == "FAIL" and name != "use":
            structure.errors.append(f"{name} is unavailable or structurally invalid")
    structure.status = "FAIL" if structure.errors else "PASS"
    accounting = SUTAccountingDiagnostics()
    fd = None
    if final_demand is not None:
        fd = final_demand if final_demand.ndim == 1 else _vector_sum(final_demand, axis=1)
    va = None
    if value_added is not None:
        va = value_added if value_added.ndim == 1 else _vector_sum(value_added, axis=0)
    use_rows = _vector_sum(use, axis=1) if use is not None else None
    use_columns = _vector_sum(use, axis=0) if use is not None else None
    commodity_total = _safe_vector_add(use_rows, fd)
    industry_total = _safe_vector_add(use_columns, va)
    accounting.commodity_balance = _check_balance(
        commodity_total,
        output_p,
        equation="output_by_product = row_sum(use) + final_demand",
        tolerance=accounting_tolerance,
    )
    accounting.industry_balance = _check_balance(
        industry_total,
        output_i,
        equation="output_by_industry = column_sum(use) + value_added",
        tolerance=accounting_tolerance,
    )
    if sut.output_by_product_scope == "domestic_output":
        accounting.make_product_balance = _check_balance(
            _vector_sum(make, axis=1) if make is not None else None,
            output_p,
            equation="output_by_product = row_sum(make)",
            tolerance=accounting_tolerance,
        )
    else:
        accounting.make_product_balance = V02BalanceCheck(
            equation="output_by_product = row_sum(make)",
            reason=(
                "make represents domestic production, but output_by_product has "
                f"scope={sut.output_by_product_scope!r}; the two cannot be compared "
                "without an explicit supply/output relationship"
            ),
        )
    accounting.make_industry_balance = _check_balance(
        _vector_sum(make, axis=0) if make is not None else None,
        output_i,
        equation="output_by_industry = column_sum(make)",
        tolerance=accounting_tolerance,
    )
    accounting.status = _final_status(
        [
            accounting.commodity_balance,
            accounting.industry_balance,
            accounting.make_product_balance,
            accounting.make_industry_balance,
        ]
    )
    accounting.notes.append(
        "SUT blocks are audited directly; no automatic SUT-to-SIOT transformation is performed"
    )
    accounting.notes.append(
        f"output_by_product scope declared as {sut.output_by_product_scope!r}"
    )
    if supply is not None:
        accounting.notes.append("supply was structurally checked but not assigned an accounting identity")
    metadata = diagnose_metadata(sut.metadata)
    warnings = list(structure.warnings) + list(accounting.notes) + list(metadata.notes)
    errors = list(structure.errors)
    return SUTAuditReport(
        system_type="SUT",
        structure=structure,
        accounting=accounting,
        coefficients=None,
        stability=None,
        reference=None,
        metadata=metadata,
        methods={"numerical_method": "not_applicable"},
        provenance=_report_provenance(sut, "SUT", accounting_tolerance),
        warnings=warnings,
        errors=errors,
    )


def audit_mrio(
    mrio: MRIOSystem,
    *,
    numerical_method: str = "auto",
    accounting_tolerance: dict[str, float] | None = None,
) -> SystemAuditReport:
    """Audit an MRIO already expanded to one region-sector axis."""

    if not isinstance(mrio, MRIOSystem):
        raise IOValidationError("audit_mrio expects an MRIOSystem instance")
    r, s, n = len(mrio.regions), len(mrio.sectors), len(mrio.labels)
    structure = MRIOStructureDiagnostics(
        n_regions=r,
        n_sectors=s,
        n_total=n,
        expected_labels=mrio.labels,
    )
    if r == 0 or s == 0:
        structure.errors.append("regions and sectors must both be non-empty")
    if len(set(map(str, mrio.regions))) != r:
        structure.errors.append("duplicate region labels")
    if len(set(map(str, mrio.sectors))) != s:
        structure.errors.append("duplicate sector labels")
    z, structure.fields["Z"] = _validate_value(
        mrio.Z,
        expected_shapes={(n, n)},
        row_labels=mrio.labels,
        column_labels=mrio.labels,
    )
    x, structure.fields["x"] = _validate_value(
        mrio.x,
        expected_shapes={(n,)},
        row_labels=mrio.labels,
    )
    y, structure.fields["Y"] = _validate_value(
        mrio.Y,
        shape_validator=lambda shape: len(shape) == 1 and shape == (n,)
        or len(shape) == 2 and shape[0] == n,
        row_labels=mrio.labels,
    )
    v, structure.fields["V"] = _validate_value(
        mrio.V,
        shape_validator=lambda shape: len(shape) == 1 and shape == (n,)
        or len(shape) == 2 and shape[1] == n,
        column_labels=mrio.labels,
    )
    core_field_names = {"Z", "x"}
    for name, info in structure.fields.items():
        if info.get("status") == "FAIL":
            message = f"{name} is unavailable or structurally invalid"
            if name in core_field_names:
                structure.errors.append(message)
            else:
                structure.supporting_failures.append(message)
    if z is not None:
        blocks: list[dict[str, Any]] = []
        for row_region in range(r):
            for column_region in range(r):
                block = z[
                    row_region * s : (row_region + 1) * s,
                    column_region * s : (column_region + 1) * s,
                ]
                blocks.append(
                    {
                        "row_region": mrio.regions[row_region],
                        "column_region": mrio.regions[column_region],
                        "shape": list(block.shape),
                        "finite": bool(_all_finite(block)),
                    }
                )
        structure.block_structure = {
            "region_block_count": r * r,
            "block_size": [s, s],
            "blocks": blocks,
            "domestic_block_count": r,
            "offdiagonal_block_count": max(0, r * r - r),
        }
    else:
        structure.block_structure = {"region_block_count": r * r, "block_size": [s, s]}
    structure.status = "FAIL" if structure.errors else "PASS"
    has_supporting_inputs = mrio.Y is not None or mrio.V is not None
    if not has_supporting_inputs:
        structure.supporting_status = "SKIPPED"
    else:
        structure.supporting_status = (
            "FAIL" if structure.supporting_failures else "PASS"
        )
    accounting = MRIOAccountingDiagnostics()
    fd = None
    if y is not None:
        fd = y if y.ndim == 1 else _vector_sum(y, axis=1)
    va = None
    if v is not None:
        va = v if v.ndim == 1 else _vector_sum(v, axis=0)
    z_rows = _vector_sum(z, axis=1) if z is not None else None
    z_columns = _vector_sum(z, axis=0) if z is not None else None
    accounting.output_balance = _check_balance(
        _safe_vector_add(z_rows, fd),
        x,
        equation="x = row_sum(Z) + row_sum(Y)",
        tolerance=accounting_tolerance,
    )
    accounting.input_balance = _check_balance(
        _safe_vector_add(z_columns, va),
        x,
        equation="x = column_sum(Z) + column_sum(V)",
        tolerance=accounting_tolerance,
    )
    accounting.status = _final_status([accounting.output_balance, accounting.input_balance])
    accounting.notes.append(
        "MRIO accounting treats cross-region flows as embedded in the supplied Z and Y blocks"
    )
    method = _select_method(
        numerical_method,
        n if z is not None else None,
        sparse_input=_is_sparse(mrio.Z),
    )
    core_safe = (
        structure.status == "PASS"
        and z is not None
        and x is not None
        and structure.fields.get("Z", {}).get("status") == "PASS"
        and structure.fields.get("x", {}).get("status") == "PASS"
    )
    coefficients = diagnose_coefficients(
        z,
        x,
        alignment_safe=core_safe,
        alignment_reason=(
            "Z, x, or their region-sector labels are not safely aligned; "
            "coefficients are SKIPPED"
            if not core_safe
            else None
        ),
    )
    stability = diagnose_stability(coefficients.A, numerical_method=method)
    proxy = SimpleNamespace(
        A_reference=mrio.A_reference,
        L_reference=mrio.L_reference,
        Z=mrio.Z,
        sectors=mrio.labels,
    )
    reference = diagnose_reference(proxy, coefficients.A, stability.leontief_inverse)
    metadata = diagnose_metadata(mrio.metadata)
    warnings = list(accounting.notes) + list(metadata.notes)
    warnings.extend(
        f"supporting input issue: {message}"
        for message in structure.supporting_failures
    )
    if reference.status in {"FAIL", "AVAILABLE"}:
        warnings.append("optional MRIO reference validation requires separate review")
    errors = list(structure.errors)
    methods = {
        "numerical_method": method,
        "spectral_radius": method,
        "condition_number": method,
        "spectral_radius_exact": stability.spectral_radius_exact,
        "condition_number_exact": stability.condition_number_exact,
    }
    return MRIOAuditReport(
        system_type="MRIO",
        structure=structure,
        accounting=accounting,
        coefficients=coefficients,
        stability=stability,
        reference=reference,
        metadata=metadata,
        methods=methods,
        provenance=_report_provenance(mrio, "MRIO", accounting_tolerance),
        warnings=warnings,
        errors=errors,
    )


class SUTAuditReport(SystemAuditReport):
    """Named report type for :func:`audit_sut`."""


class MRIOAuditReport(SystemAuditReport):
    """Named report type for :func:`audit_mrio`."""
