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
from .structure import _core_inputs_are_safe, _is_sparse, diagnose_structure
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
    core_inputs_safe = _core_inputs_are_safe(structure)
    dependent_z = z if core_inputs_safe else None
    dependent_x = x if core_inputs_safe else None
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
    zero_structure = diagnose_zero_output(
        dependent_z, dependent_x, list(io.sectors), io.Y, io.V
    )
    accounting = diagnose_accounting(
        z,
        x,
        io,
        io.accounting,
        list(io.sectors),
        tolerance=accounting_tolerance,
        components=components,
        structure=structure,
    )
    metadata = diagnose_metadata(io.metadata)
    orientation = diagnose_orientation(io, z, x, structure, components)
    coefficients = diagnose_coefficients(
        z,
        x,
        alignment_safe=core_inputs_safe,
        alignment_reason=(
            "Z, x, or their sector labels are not safely aligned; coefficients are SKIPPED"
            if not core_inputs_safe
            else None
        ),
    )
    stability = diagnose_stability(coefficients.A, numerical_method=method)
    reference = diagnose_reference(io, coefficients.A, stability.leontief_inverse)
    signs = diagnose_signs(io)
    scale = diagnose_scale(
        dependent_z,
        dependent_x,
        io,
        accounting,
        list(io.sectors),
        reference_diagnostics=reference,
    )

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
    warnings.extend(structure.details.get("normalized_label_warnings", []))
    warnings.extend(getattr(structure, "supporting_warnings", []))
    warnings.extend(
        f"supporting input issue: {message}"
        for message in getattr(structure, "supporting_failures", [])
    )
    if components.double_count_risk:
        warnings.append(
            "Y/V subtotal components may be double-counted; inspect report.components.double_count_risk"
        )
    if getattr(components, "component_label_risks", []):
        warnings.append(
            "Y/V component labels may be ambiguous; inspect report.components.component_label_risks"
        )
    if getattr(scale, "status", None) in {"AVAILABLE", "WARNING"} and getattr(
        scale, "cell_status", None
    ) == "SKIPPED":
        warnings.append(
            "cell scale diagnostics skipped: rounding context unavailable"
        )
    if structure.possible_nonsector_rows or structure.possible_nonsector_columns:
        warnings.append("possible non-sector labels were found in Z")
    if structure.possible_duplicate_rows or structure.possible_duplicate_columns:
        warnings.append("exact duplicate rows or columns were found in Z")
    if structure.duplicate_labels_after_normalization:
        warnings.append("duplicate labels remain after Unicode/whitespace normalization")
    exact = getattr(structure, "input_adjustment_labels_match", None)
    normalized = getattr(structure, "normalized_input_adjustment_labels_match", None)
    if exact is False and normalized is True:
        warnings.append(
            "input_adjustments labels match sectors only after Unicode/whitespace normalization"
        )
    if zero_structure.all_zero_rows_with_positive_output or zero_structure.all_zero_columns_with_positive_output:
        warnings.append("Z contains all-zero rows or columns with positive output")
    if zero_structure.all_zero_rows_with_positive_final_demand:
        warnings.append("Z contains all-zero rows with positive final-demand evidence")
    if zero_structure.all_zero_columns_with_positive_value_added:
        warnings.append("Z contains all-zero columns with positive value-added evidence")
    if zero_structure.isolated_sectors:
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
        zero_structure=zero_structure,
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
