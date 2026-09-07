"""Top-level audit orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from .accounting import diagnose_accounting
from .coefficients import diagnose_coefficients
from .components import diagnose_components
from .exceptions import IOValidationError
from .metadata import diagnose_metadata
from .model import IOSystem
from .orientation import diagnose_orientation
from .provenance import build_provenance
from .reference import diagnose_reference
from .results import AuditReport
from .scale import diagnose_scale
from .signs import diagnose_signs
from .stability import diagnose_stability
from .structure import _is_sparse, diagnose_structure
from .zero_output import diagnose_zero_output


@dataclass
class MethodsDiagnostics:
    """Numerical routes selected for this audit."""

    numerical_method: str = "dense"
    spectral_radius: str = "dense"
    condition_number: str = "dense"
    spectral_radius_exact: bool | None = None
    condition_number_exact: bool | None = None


def _select_method(requested: str, n: int | None, *, sparse_input: bool = False) -> str:
    if requested not in {"auto", "dense", "iterative"}:
        raise IOValidationError("numerical_method must be 'auto', 'dense', or 'iterative'")
    if requested == "auto":
        return "iterative" if sparse_input or (n is not None and n > 200) else "dense"
    return requested


def audit(
    io: IOSystem,
    numerical_method: str = "auto",
    accounting_tolerance: dict[str, float] | None = None,
) -> AuditReport:
    """Run all v0.1 diagnostics and return an :class:`AuditReport`.

    The audit is read-only with respect to ``io``.  Any calculation requiring
    a malformed or non-finite input is represented as SKIPPED in the result.
    """

    if not isinstance(io, IOSystem):
        raise IOValidationError("audit expects an IOSystem instance")
    structure, arrays = diagnose_structure(io)
    z = arrays.get("Z")
    x = arrays.get("x")
    method = _select_method(
        numerical_method,
        structure.n_rows if structure.z_is_square == "PASS" else None,
        sparse_input=_is_sparse(io.Z),
    )
    methods = MethodsDiagnostics(
        numerical_method=method,
        spectral_radius=method,
        condition_number=method,
    )

    components = diagnose_components(io)
    zero_output = diagnose_zero_output(z, x, list(io.sectors), io.Y, io.V)
    accounting = diagnose_accounting(
        z,
        x,
        io,
        io.accounting,
        list(io.sectors),
        tolerance=accounting_tolerance,
        components=components,
    )
    metadata = diagnose_metadata(io.metadata)
    orientation = diagnose_orientation(io, z, x, structure, components)
    coefficients = diagnose_coefficients(z, x)
    stability = diagnose_stability(coefficients.A, numerical_method=method)
    reference = diagnose_reference(io, coefficients.A, stability.leontief_inverse)
    signs = diagnose_signs(io)
    scale = diagnose_scale(z, x, io, accounting, list(io.sectors))

    methods.spectral_radius_exact = stability.spectral_radius_exact
    methods.condition_number_exact = stability.condition_number_exact
    provenance = build_provenance(
        io,
        methods,
        requested_numerical_method=numerical_method,
        accounting_tolerance=getattr(accounting, "tolerance", None),
        scale=scale,
    )
    warnings: list[str] = []
    errors: list[str] = []
    warnings.extend(accounting.notes)
    warnings.extend(metadata.notes)
    if components.double_count_risk:
        warnings.append(
            "Y/V subtotal components may be double-counted; inspect report.components.double_count_risk"
        )
    if (
        getattr(scale, "status", None) == "AVAILABLE"
        and getattr(scale, "cell_status", None) == "SKIPPED"
    ):
        warnings.append(
            "cell scale diagnostics skipped: rounding context unavailable"
        )
    if structure.possible_nonsector_rows or structure.possible_nonsector_columns:
        warnings.append("possible non-sector labels were found in Z")
    if structure.possible_duplicate_rows or structure.possible_duplicate_columns:
        warnings.append("exact duplicate rows or columns were found in Z")
    if structure.duplicate_labels_after_normalization:
        warnings.append("duplicate labels remain after Unicode/whitespace normalization")
    if zero_output.all_zero_rows_with_positive_output or zero_output.all_zero_columns_with_positive_output:
        warnings.append("Z contains all-zero rows or columns with positive output")
    if zero_output.all_zero_rows_with_positive_final_demand:
        warnings.append("Z contains all-zero rows with positive final-demand evidence")
    if zero_output.all_zero_columns_with_positive_value_added:
        warnings.append("Z contains all-zero columns with positive value-added evidence")
    if zero_output.isolated_sectors:
        warnings.append("isolated sectors were found from available Z/Y/V evidence")
    if orientation.possible_transpose is None:
        warnings.append("possible_transpose is indeterminate from available evidence")
    if stability.reason and method == "iterative":
        warnings.append(stability.reason)
    if structure.status == "FAIL":
        errors.append("structural validation failed; dependent calculations may be SKIPPED")

    return AuditReport(
        structure=structure,
        orientation=orientation,
        accounting=accounting,
        signs=signs,
        zero_output=zero_output,
        coefficients=coefficients,
        stability=stability,
        reference=reference,
        scale=scale,
        components=components,
        metadata=metadata,
        provenance=provenance,
        methods=methods,
        warnings=warnings,
        errors=errors,
    )
