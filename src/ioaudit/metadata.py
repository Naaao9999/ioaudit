"""Semantic metadata completeness diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .semantics import PriceBasis


@dataclass
class MetadataDiagnostics:
    """Record semantic metadata and its machine-readable price basis."""

    status: str = "WARNING"
    values: dict[str, Any] = field(default_factory=dict)
    required_fields: list[str] = field(
        default_factory=lambda: ["year", "unit", "price_basis"]
    )
    recommended_fields: list[str] = field(
        default_factory=lambda: [
            "currency",
            "valuation",
            "symmetric_dimension",
            "classification",
        ]
    )
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    invalid_fields: list[str] = field(default_factory=list)
    price_basis: PriceBasis | None = None
    price_basis_status: str = "MISSING"
    notes: list[str] = field(default_factory=list)


def diagnose_metadata(metadata: Any) -> MetadataDiagnostics:
    """Report missing semantic metadata without inferring any values."""

    result = MetadataDiagnostics()
    if not isinstance(metadata, dict):
        result.missing_required = list(result.required_fields)
        result.missing_recommended = list(result.recommended_fields)
        result.notes.append("metadata was not supplied")
        return result
    result.values = dict(metadata)

    def _missing(name: str) -> bool:
        value = metadata.get(name)
        return value is None or (isinstance(value, str) and not value.strip())

    result.missing_required = [name for name in result.required_fields if _missing(name)]
    result.missing_recommended = [name for name in result.recommended_fields if _missing(name)]

    raw_price_basis = metadata.get("price_basis")
    if _missing("price_basis"):
        result.price_basis_status = "MISSING"
    else:
        parsed_price_basis = PriceBasis.parse(raw_price_basis)
        if parsed_price_basis is None:
            result.price_basis_status = "INVALID"
            result.invalid_fields.append("price_basis")
            result.notes.append(
                "price_basis must be one of: "
                + ", ".join(item.value for item in PriceBasis)
            )
        else:
            result.price_basis = parsed_price_basis
            result.price_basis_status = (
                "UNKNOWN" if parsed_price_basis is PriceBasis.UNKNOWN else "DECLARED"
            )
            # Keep serialized metadata deterministic when callers use the enum.
            result.values["price_basis"] = parsed_price_basis.value
            if parsed_price_basis is PriceBasis.UNKNOWN:
                result.notes.append("price_basis was explicitly declared as unknown")
    if result.missing_required:
        result.notes.append("missing required semantic metadata: " + ", ".join(result.missing_required))
    if result.missing_recommended:
        result.notes.append("missing recommended semantic metadata: " + ", ".join(result.missing_recommended))
    result.status = (
        "PASS"
        if (
            not result.missing_required
            and not result.invalid_fields
            and result.price_basis_status != "UNKNOWN"
        )
        else "WARNING"
    )
    return result
